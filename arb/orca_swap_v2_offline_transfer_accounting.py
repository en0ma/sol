"""Validate simulated Token-2022 transfer post-balances without broadcasting."""
def reconcile_transfer_simulation(value, *, amount, initial_source, initial_destination):
    if not isinstance(value, dict) or value.get("err") is not None:
        raise ValueError("successful simulation result required")
    if any(type(x) is not int or x < 0 or x >= 2**64 for x in
           (amount, initial_source, initial_destination)) or amount <= 0:
        raise ValueError("invalid token amounts")
    accounts = value.get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 2:
        return {"status": "POST_ACCOUNTS_NOT_RETURNED",
                "post_token_balances_verified": False,
                "signed_swap_simulation_verified": False, "broadcast": False}
    import base64
    observed = []
    for account in accounts:
        data = account.get("data") if isinstance(account, dict) else None
        if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
            raise ValueError("invalid simulated account data")
        raw = base64.b64decode(data[0], validate=True)
        if len(raw) < 165 or raw[108] != 1:
            raise ValueError("invalid simulated token account")
        observed.append(int.from_bytes(raw[64:72], "little"))
    expected = [initial_source - amount, initial_destination + amount]
    verified = initial_source >= amount and observed == expected
    return {"status": "TRANSFER_BALANCES_RECONCILED" if verified else "TRANSFER_BALANCES_MISMATCH",
            "expected_post_balances_base_units": expected,
            "observed_post_balances_base_units": observed,
            "post_token_balances_verified": verified,
            "signed_swap_simulation_verified": False,
            "broadcast": False}
