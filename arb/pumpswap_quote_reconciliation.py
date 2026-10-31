"""Compare successful signed PumpSwap simulation balances to diagnostic quote candidates.

A matching amount is evidence for one test amount, not a validated fee mode,
quote formula, executable adapter or arbitrage profit. Fail closed otherwise.
"""
from arb.pumpswap_quote_interval import quote_candidate_interval


def reconcile_simulation(pool, mint_in, requested_amount, simulated):
    if not isinstance(simulated,dict) or simulated.get("simulation_verified") is not True:
        raise ValueError("successful signed simulation required")
    spent=simulated.get("spent_base_units")
    received=simulated.get("received_base_units")
    if (type(spent) is not int or type(received) is not int
            or type(requested_amount) is not int
            or spent<=0 or spent>requested_amount or received<=0):
        raise ValueError("invalid simulated token deltas")
    # A buy_exact_quote_in may spend less than the requested upper bound;
    # compare quote mathematics to actual expenditure, never the ceiling.
    diagnostic=quote_candidate_interval(pool,mint_in,spent)
    options=diagnostic["candidate_outputs"]
    matching=[mode for mode,amount in options.items() if amount==received]
    return {"status":"CANDIDATE_MATCH_OBSERVED" if matching else "QUOTE_MISMATCH",
            "spent_base_units":spent,"received_base_units":received,
            "candidate_outputs":options,"matching_modes":matching,
            "fee_modes_complete":not bool(diagnostic.get("unavailable_modes")),
            "simulation_verified":True,"quote_reconciled":False,
            "effective_fee_verified":False,"profitable_arbitrage_verified":False,
            "actionable":False}
