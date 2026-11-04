"""Independent exact-integer continuity audit of source-bound route quote reports.

This checks arithmetic and identity consistency, not whether native SDK pricing
is correct; only signed offline SPL deltas can establish actual execution.
No coordinator admission or mainnet approval is emitted.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
MAX_U64=2**64

def audit_ranked_source_quote_continuity(ranking, fixtures, amount_in):
    if (not isinstance(ranking,dict) or
        ranking.get("status")!="GROSS_SOURCE_BOUND_RANKING_ONLY" or
        any(ranking.get(k) is not False for k in SAFE) or
        not isinstance(fixtures,list) or len(fixtures)>100 or
        type(amount_in)is not int or not 0<amount_in<MAX_U64 or
        not isinstance(ranking.get("ranked"),list) or
        len(ranking["ranked"])>len(fixtures)):
        raise ValueError("untrusted native quote research handoff")
    checked=[]
    seen=set()
    last_margin=None
    for row in ranking["ranked"]:
        if not isinstance(row,dict) or row.get("status")!="GROSS_INDICATIVE_ONLY":
            raise ValueError("untrusted source quote row")
        idx=row.get("index")
        if type(idx)is not int or not 0<=idx<len(fixtures) or idx in seen:
            raise ValueError("duplicate or invalid quote fixture index")
        seen.add(idx)
        fixture=fixtures[idx]
        mints=fixture.get("route_mints")
        venues=fixture.get("route_venues")
        pools=fixture.get("route_pool_addresses")
        slot=fixture.get("state_accounts_observed_slot")
        quotes=row.get("quotes")
        if (not isinstance(mints,list) or len(mints)!=4 or mints[0]!=mints[-1] or
            not isinstance(venues,list) or len(venues)!=3 or len(set(venues))!=3 or
            not isinstance(pools,list) or len(pools)!=3 or len(set(pools))!=3 or
            type(slot)is not int or slot<0 or
            not isinstance(quotes,list) or len(quotes)!=3 or
            row.get("start_mint")!=mints[0] or
            type(row.get("input_base_units"))is not int or
            row["input_base_units"]!=amount_in or
            row.get("net_profitability_confirmed") is not False or
            any(row.get(k) is not False for k in SAFE)):
            raise ValueError("source quote topology or slot mismatch")
        current=amount_in
        for leg,q in enumerate(quotes):
            if (not isinstance(q,dict) or
                q.get("venue")!=venues[leg] or q.get("pool")!=pools[leg] or
                q.get("input_mint")!=mints[leg] or
                q.get("output_mint")!=mints[leg+1] or
                q.get("source_slot")!=slot or
                type(q.get("amount_out"))is not int or
                not 0<q["amount_out"]<MAX_U64):
                raise ValueError("quoted leg identity, amount or source state invalid")
            current=q["amount_out"]
        margin=current-amount_in
        if (type(row.get("output_base_units"))is not int or
            row["output_base_units"]!=current or
            type(row.get("gross_delta_start_mint_base_units"))is not int or
            row["gross_delta_start_mint_base_units"]!=margin or
            row.get("positive_gross") is not (margin>0) or
            last_margin is not None and margin>last_margin):
            raise ValueError("route quote integer gross accounting mismatch")
        last_margin=margin
        checked.append({"index":idx,"hops":3,"source_slot":slot,
                        "gross_start_mint_base_units":margin,
                        "arithmetic_checked":True,"native_pricing_independently_audited":False,
                        "signed_execution_verified":False,"coordinator_eligible":False})
    return {"status":"SOURCE_QUOTE_CONTINUITY_ARITHMETIC_ONLY",
            "checked_routes":len(checked),"routes":checked,
            "current_native_sdk_parity_verified":False,
            "coordinator_eligible_routes":0,**SAFE}
