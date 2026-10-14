"""Deterministic arithmetic for executable-quote arbitrage research."""
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class Quote:
    venue: str
    input_mint: str
    output_mint: str
    in_amount: int
    out_amount: int

def evaluate_cycle(quotes: list[Quote], start_amount: int, cost_in_start_units: int = 0) -> dict:
    """Amounts are integer token base units. Cost must be denominated in starting mint units."""
    if not quotes or start_amount <= 0 or cost_in_start_units < 0:
        raise ValueError("invalid cycle")
    if quotes[0].in_amount != start_amount:
        raise ValueError("starting amount mismatch")
    for prior, nxt in zip(quotes, quotes[1:]):
        if prior.output_mint != nxt.input_mint or prior.out_amount != nxt.in_amount:
            raise ValueError("disconnected route")
    if quotes[-1].output_mint != quotes[0].input_mint:
        raise ValueError("cycle does not end in starting mint")
    if any(q.in_amount <= 0 or q.out_amount <= 0 for q in quotes):
        raise ValueError("nonpositive quote")
    gross = quotes[-1].out_amount - start_amount
    net = gross - cost_in_start_units
    return {"gross_profit_units": gross, "estimated_net_units": net,
            "gross_return_bps": str(Decimal(gross) * 10000 / Decimal(start_amount)),
            "profitable": net > 0, "venues": [q.venue for q in quotes]}
