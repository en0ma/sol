"""Bound first initialized Orca tick crossing in exact-input base units.

This diagnostic derives the fee-inclusive input to reach the first observed
initialized tick from a decoded pool. It does not prove executable rounding,
account freshness or ability to fund a swap; no transactions are sent.
"""
from arb.orca_tick_math import sqrt_price_from_tick_index
from arb.orca_multitick_quote import Q, FEE_DENOM, _ceil
from arb.whirlpool_ticks import directional_tick_observation


def first_crossing_budget(state, mint_in, arrays, *, simulation_cap=100000000):
    if type(simulation_cap) is not int or not 0 < simulation_cap < 1 << 64:
        raise ValueError("invalid simulation cap")
    a, b = state["token_mint_a"], state["token_mint_b"]
    if mint_in not in (a, b):
        raise ValueError("invalid input mint")
    current, spacing = state["tick_current_index"], state["tick_spacing"]
    direction = "a_to_b" if mint_in == a else "b_to_a"
    observation = directional_tick_observation(arrays, current, spacing, direction)
    report = {"status": observation["status"], "direction": direction,
              "first_tick": observation["first_tick"],
              "candidate_input_base_units": None, "within_simulation_cap": False,
              "actionable": False, "executable_quote": False}
    if observation["status"] != "OBSERVED_INITIALIZED_TICK":
        return report
    p = int(state["sqrt_price_x64"])
    liquidity = int(state["liquidity"])
    fee = state["fee_rate_hundredths_bps"]
    if not 0 < p < 1 << 128 or not 0 < liquidity < 1 << 128:
        raise ValueError("invalid price or liquidity")
    if type(fee) is not int or not 0 <= fee < FEE_DENOM:
        raise ValueError("invalid fee")
    target = sqrt_price_from_tick_index(observation["first_tick"])
    down = direction == "a_to_b"
    if not (target < p if down else target > p):
        return {**report, "status": "TICK_AT_OR_BEYOND_CURRENT_PRICE"}
    required_net = (_ceil(liquidity * Q * (p-target), p*target)
                    if down else _ceil(liquidity * (target-p), Q))
    gross = _ceil(required_net * FEE_DENOM, FEE_DENOM-fee)
    if not 0 < gross < 1 << 64:
        raise ValueError("crossing threshold out of bounds")
    return {**report, "status": "CROSSING_BUDGET_ESTIMATE",
            "candidate_input_base_units": gross,
            "within_simulation_cap": gross <= simulation_cap}
