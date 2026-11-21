"""Assemble (but never send) a closed multi-hop Orca Whirlpool instruction list.

Caller must supply funded token accounts, signed-safe amounts and independently
verified per-hop state. This module makes NO quote or profitability claims.
"""
from arb.whirlpool_swap import build_swap
from arb.orca_whirlpool import SOL, USDC

MAX_HOPS = 3

def assemble_orca_cycle(route, pool_states, oracles, user_accounts,
                        authority, amounts, min_outputs):
    legs = route.get("legs", [])
    tokens = route.get("tokens", [])
    if not 2 <= len(legs) <= MAX_HOPS or len(tokens) != len(legs) + 1:
        raise ValueError("cycle must contain two or three legs")
    if tokens[0] not in (SOL, USDC) or tokens[-1] != tokens[0]:
        raise ValueError("cycle must close in its SOL or USDC starting mint")
    if len(set((leg["pool"] for leg in legs))) != len(legs):
        raise ValueError("pool reuse disabled")
    if len(amounts) != len(legs) or len(min_outputs) != len(legs):
        raise ValueError("per-hop amounts and thresholds required")
    if set(tokens[:-1]) - set(user_accounts):
        raise ValueError("missing user account for intermediate token")
    if not isinstance(authority, str) or not authority:
        raise ValueError("authority missing")
    instructions = []
    for i, leg in enumerate(legs):
        if leg.get("venue") != "orca" or (leg["from"], leg["to"]) != (tokens[i], tokens[i+1]):
            raise ValueError("unsupported or disconnected leg")
        state = pool_states[leg["pool"]]
        a, b = state["token_mint_a"], state["token_mint_b"]
        if (leg["from"], leg["to"]) == (a, b):
            a_to_b = True
        elif (leg["from"], leg["to"]) == (b, a):
            a_to_b = False
        else:
            raise ValueError("pool mints do not match graph leg")
        if type(amounts[i]) is not int or not 0 < amounts[i] < 1 << 64:
            raise ValueError("invalid hop amount")
        if type(min_outputs[i]) is not int or not 0 < min_outputs[i] < 1 << 64:
            raise ValueError("invalid nonzero minimum output")
        instructions.append(build_swap(
            leg["pool"], state, authority, user_accounts[a], user_accounts[b],
            oracles[leg["pool"]], amounts[i], min_outputs[i],
            a_to_b=a_to_b, amount_specified_is_input=True))
    return instructions
