"""Strict comparison of indicative Orca quotes with signed local Surfpool results.

Only observed post-simulation SPL balances count as execution evidence.
Successful simulation does not imply profitable arbitrage or verified quoting
for other pool states, trade sizes, or tick crossings.
"""


def compare_quote_and_simulation(quote, simulation, *, max_error_units=0):
    if type(max_error_units) is not int or max_error_units < 0:
        raise ValueError("invalid error tolerance")
    if not isinstance(quote, dict) or not isinstance(simulation, dict):
        raise ValueError("missing comparison evidence")
    if quote.get("status") != "INDICATIVE_MULTITICK_ONLY":
        raise ValueError("unsupported quote provenance")
    if quote.get("actionable") is not False or quote.get("executable_quote") is not False:
        raise ValueError("quote incorrectly marked executable")
    if (simulation.get("status") != "PASS" or
            simulation.get("swap_success") is not True or
            simulation.get("program_invoked") is not True or
            simulation.get("local_only") is not True):
        raise ValueError("successful signed local simulation required")
    balances = simulation.get("token_balance_changes")
    if not isinstance(balances, dict):
        raise ValueError("missing observed token balances")
    for key in ("estimated_output_base_units", "amount_in"):
        if type(quote.get(key)) is not int or quote[key] <= 0:
            raise ValueError("invalid quoted amount")
    for key in ("input_amount_base_units", "spent_base_units", "received_base_units"):
        if type(balances.get(key)) is not int or balances[key] <= 0:
            raise ValueError("invalid simulated amount")
    if (quote.get("mint_in") != balances.get("input_mint") or
            quote.get("mint_out") != balances.get("output_mint") or
            quote["amount_in"] != balances["input_amount_base_units"] or
            balances["spent_base_units"] != quote["amount_in"]):
        raise ValueError("quote and simulated swap identity mismatch")
    observed = balances["received_base_units"]
    predicted = quote["estimated_output_base_units"]
    error = observed - predicted
    return {
        "status": "MATCH" if abs(error) <= max_error_units else "MISMATCH",
        "predicted_output_base_units": predicted,
        "observed_output_base_units": observed,
        "absolute_error_base_units": abs(error),
        "signed_error_base_units": error,
        "tolerance_base_units": max_error_units,
        "simulation_only": True,
        "single_observation": True,
        "executable_quote": False,
        "actionable": False,
        "confirmed_profitable": False,
    }
