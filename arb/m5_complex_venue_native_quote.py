"""Source-fixture-gated native quote interfaces for the three complex venues.

Actual fee, bin-array and effective reserve evidence MUST be decoded from
captured same-slot chain accounts. Missing fields fail closed; never substitute
vault-CPMM estimates or defaults. Native math remains research-indicative.
"""
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
SUPPORTED=frozenset(("meteora_dlmm","meteora_damm_v2","pumpswap"))

def quote_auxiliary(fixture, row, *, venue, mint_in, amount_in, auxiliary):
    verify(fixture)
    if (venue not in SUPPORTED or row.get("venue")!=venue
            or type(amount_in)is not int or not 0<amount_in<2**64
            or mint_in not in row.get("mints",())
            or not isinstance(auxiliary,dict)):
        raise ValueError("invalid source-bound native auxiliary quote request")
    slot=fixture["state_accounts_observed_slot"]
    # Auxiliary derived pricing is valid only if the decoder attached
    # independent account IDs from the current manifest and identical slot.
    addresses=auxiliary.get("source_account_addresses")
    if (type(auxiliary.get("snapshot_slot"))is not int
            or auxiliary["snapshot_slot"]!=slot
            or not isinstance(addresses,list) or not addresses
            or len(addresses)!=len(set(addresses))
            or any(not isinstance(a,str) or a not in fixture["state_account_addresses"]
                   for a in addresses)
            or row["address"] not in addresses
            or auxiliary.get("native_state_decoder_authenticated") is not True):
        raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: authenticated same-slot decoder and account bindings required")
    if any(fixture["accounts"][a] is None for a in addresses):
        raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: captured source account not present")
    state=row["decoded_pool_state"]
    if venue=="meteora_dlmm":
        from arb.meteora_dlmm_bin_quote import quote_bins
        required=("bins","total_fee_rate","swap_x_for_y")
        if any(k not in auxiliary for k in required):
            raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: active and traversed DLMM bins and variable fee")
        swap=mint_in==state["token_x_mint"]
        if auxiliary["swap_x_for_y"] is not swap:
            raise ValueError("DLMM swap direction conflicts with decoded pool mint")
        bins=auxiliary["bins"]
        if not bins or bins[0].get("bin_id")!=state["active_id"]:
            raise ValueError("DLMM active bin does not match source pool")
        result=quote_bins(amount_in=amount_in,swap_x_for_y=swap,
                          bins=bins,total_fee_rate=auxiliary["total_fee_rate"])
        output=result["amount_out"]
    elif venue=="meteora_damm_v2":
        from arb.meteora_damm_v2_quote import quote_collection_mode
        if any(k not in auxiliary for k in ("vault_base_units","effective_fee_ppm","collection_mode")):
            raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: DAMM fee scheduler, collection mode and reserves")
        reserves=auxiliary["vault_base_units"]
        if not isinstance(reserves,list) or len(reserves)!=2:
            raise ValueError("DAMM native source vaults missing")
        result=quote_collection_mode(reserves[0],reserves[1],amount_in,
            input_is_a=mint_in==state["token_a_mint"],
            effective_fee_ppm=auxiliary["effective_fee_ppm"],
            collection_mode=auxiliary["collection_mode"])
        output=result["amount_out"]
    else:
        from arb.pumpswap_quote import quote_exact_input
        if "verified_total_fee_ppm" not in auxiliary or "pool" not in auxiliary:
            raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: PumpSwap dynamic fee and fee buckets")
        pool=auxiliary["pool"]
        if (not isinstance(pool,dict) or pool.get("base_mint")!=state["base_mint"]
                or pool.get("quote_mint")!=state["quote_mint"]):
            raise ValueError("PumpSwap fee state mint mismatch")
        result=quote_exact_input(pool,mint_in,amount_in,
                   verified_total_fee_ppm=auxiliary["verified_total_fee_ppm"])
        output=result["estimated_output_base_units"]
    if type(output)is not int or output<=0:
        raise ValueError("native quote output invalid")
    return {"venue":venue,"pool":row["address"],"input_mint":mint_in,
            "amount_in":amount_in,"amount_out":output,"snapshot_slot":slot,
            "protocol_exact_verified":False,**SAFE}
