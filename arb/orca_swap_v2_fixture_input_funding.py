"""Conservative token input funding check from synchronized account readback.

Balance sufficiency is not swap readiness: fees, rent, quote and signer custody
remain separate validation requirements.
"""

def check_fixture_input_funding(readback, *, a_to_b, required_amount):
    if not isinstance(readback, dict) or readback.get("status") != "FIXTURE_USER_ACCOUNTS_READBACK_VERIFIED":
        raise ValueError("authenticated fixture token readback required")
    if type(a_to_b) is not bool or type(required_amount) is not int or not 0 < required_amount < 2**64:
        raise ValueError("invalid swap direction or input amount")
    balances = readback.get("observed_balances_base_units")
    if (not isinstance(balances, list) or len(balances) != 2 or
            any(type(v) is not int or v < 0 or v >= 2**64 for v in balances)):
        raise ValueError("invalid synchronized token balances")
    if type(readback.get("balance_snapshot_slot")) is not int or (
            readback["balance_snapshot_slot"] != readback.get("user_account_snapshot_slot")):
        raise ValueError("balance snapshot context mismatch")
    selected = 0 if a_to_b else 1
    sufficient = balances[selected] >= required_amount
    return {
        "status": "INPUT_FUNDING_OBSERVED" if sufficient else "INPUT_FUNDING_INSUFFICIENT",
        "input_role": "token_owner_account_a" if a_to_b else "token_owner_account_b",
        "observed_input_balance_base_units": balances[selected],
        "required_input_base_units": required_amount,
        "input_balance_sufficient_for_gross_amount": sufficient,
        "fee_and_rent_coverage_verified": False,
        "signer_control_verified": False,
        "signed_simulation_verified": False,
        "actionable": False,
        "executable_quote": False,
        "broadcast": False,
    }
