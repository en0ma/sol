"""Deterministic fee and slippage acceptance policy for simulated swap results.

Does NOT quote, build, sign or execute AMM swaps. All values are integer
base units of the same starting token.
"""
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionBudget:
    start_amount: int
    min_end_amount: int
    network_fee: int
    priority_fee: int
    tips: int = 0

def assess(end_amount: int, budget: ExecutionBudget):
    values = (end_amount, budget.start_amount, budget.min_end_amount,
              budget.network_fee, budget.priority_fee, budget.tips)
    if any(not isinstance(value, int) or isinstance(value, bool) for value in values):
        raise TypeError("amounts must be integers")
    if budget.start_amount <= 0 or any(value < 0 for value in values):
        raise ValueError("invalid amounts or fees")
    total_fees = budget.network_fee + budget.priority_fee + budget.tips
    net = end_amount - budget.start_amount - total_fees
    return {"end_amount": end_amount, "minimum_acceptable_end": budget.min_end_amount,
            "estimated_total_fees": total_fees, "net_profit_base_units": net,
            "passes_min_output": end_amount >= budget.min_end_amount,
            "accept": end_amount >= budget.min_end_amount and net > 0}
