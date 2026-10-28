"""Backward-compatible DAMM source quote entrypoint backed ONLY by official Rust SDK.

No independent Python CPMM/fee quote. Required Pool bytes are authenticated by
the existing source manifest; absent Rust reference binary fails closed.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.source_snapshot_manifest import verify
from arb.meteora_damm_v2_native_quote import quote_pool_account
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def scenario_envelope(fixture,*,pool,mint_in,amount_in,
                      fee_rates_ppm=(0,100,1000,10000,100000),observed_unix=None):
    verify(fixture)
    if any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("unsafe source DAMM fixture")
    rows=extract_pool_states(fixture)
    row=next((r for r in rows if r["venue"]=="meteora_damm_v2"
              and r["address"]==pool),None)
    if row is None:raise ValueError("DAMM source pool not authenticated")
    if type(observed_unix)is not int or observed_unix<=0:
        raise ValueError("Meteora official quote requires observed fork unix")
    result=quote_pool_account(fixture["accounts"][pool],mint_in=mint_in,
        amount_in=amount_in,fork_unix_timestamp=observed_unix,
        fork_clock_slot=fixture["state_accounts_observed_slot"])
    return {"status":"DAMM_V2_OFFICIAL_RUST_NATIVE_QUOTE",
            "pool":pool,"source_slot":fixture["state_accounts_observed_slot"],
            "input_mint":mint_in,"input_base_units":amount_in,
            "amount_out":result["amount_out"],
            "native_pricing_engine":"OFFICIAL_METEORA_RUST_SDK",
            "protocol_exact_reference":True,
            "signed_execution_parity_verified":False,**SAFE}
