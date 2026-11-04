"""Compute source-mint net SOL economics from actual signed local-fork results.

Transaction fee remains a signed-message RPC estimate, not a paid mainnet fee.
Only wrapped native SOL starting mint admits a direct lamport conversion. SPL
start-mint costs require an independently authenticated conversion quote.
"""
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
WSOL="So11111111111111111111111111111111111111112"

def signed_net_economics(receipt, *, start_mint, source_slot,
                         fixture=None, observed_unix=None):
    if not isinstance(receipt,dict) or any(receipt.get(k)is not False for k in SAFE):
        raise ValueError("safe genuine signed simulation receipt required")
    if (type(start_mint)is not str or
            type(source_slot)is not int or source_slot<0 or
            receipt.get("state_accounts_observed_slot")!=source_slot):
        raise ValueError("signed receipt source identity mismatch")
    amounts=receipt.get("planned_inputs")
    after=receipt.get("positive_post_balances_base_units")
    if (not isinstance(amounts,list) or not amounts or
            type(amounts[0])is not int or amounts[0]<=0 or
            not isinstance(after,list) or len(after)!=len(amounts)+1 or
            any(type(v)is not int or v<0 for v in after)):
        raise ValueError("actual signed token accounting missing")
    gross=after[-1]-amounts[0]
    fee=receipt.get("signed_message_fee_estimate")
    cost=None
    reason="starting mint is not authenticated wrapped SOL; conversion remains unavailable"
    if (start_mint==WSOL and
            isinstance(fee,dict) and
            all(fee.get(k)is False for k in SAFE) and
            fee.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY" and
            fee.get("fee_payer_asset")=="SOL" and
            type(fee.get("estimated_fee_lamports"))is int and
            fee["estimated_fee_lamports"]>=0):
        cost=fee["estimated_fee_lamports"]
        reason="estimated fee priced natively in wrapped SOL; not a fee-paid or profitability receipt"
    conversion=None
    if (cost is None and start_mint!=WSOL and fixture is not None and
            type(observed_unix)is int and observed_unix>=0 and
            isinstance(fee,dict) and all(fee.get(k)is False for k in SAFE) and
            fee.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY" and
            fee.get("fee_payer_asset")=="SOL" and
            type(fee.get("estimated_fee_lamports"))is int and
            fee["estimated_fee_lamports"]>0):
        from arb.fixture_quote_execution_pipeline import extract_pool_states
        from arb.fixture_all_venue_signed_quotes import quote_leg
        if (fixture.get("state_accounts_observed_slot")!=source_slot or
                any(fixture.get(k)is not False for k in SAFE) or
                fixture.get("route_mints",[None])[0]!=start_mint):
            raise ValueError("fee conversion source manifest or starting mint mismatch")
        rows=extract_pool_states(fixture)
        mints=fixture.get("route_mints")
        if not isinstance(mints,list) or len(mints)!=len(rows)+1:
            raise ValueError("fee conversion source mint topology invalid")
        supported=frozenset(("orca","raydium_clmm","raydium_cpmm",
                             "raydium_amm_v4"))
        for i,row in enumerate(rows):
            if (row["venue"] not in supported or
                    mints[i]!=WSOL or mints[i+1]!=start_mint):
                continue
            q=quote_leg(fixture,leg_index=i,
                        amount_in=fee["estimated_fee_lamports"],
                        observed_unix=observed_unix)
            if (not isinstance(q,dict) or
                    any(q.get(k)is not False for k in SAFE) or
                    q.get("source_slot")!=source_slot or
                    q.get("venue")!=row["venue"] or
                    q.get("pool")!=row["address"]):
                raise ValueError("non-authenticated fee conversion quote")
            amount=q.get("predicted_output_base_units")
            if (q.get("quote_status")!="SOURCE_BOUND_INDICATIVE" or
                    type(amount)is not int or amount<=0):
                continue
            conversion={"status":"SOURCE_NATIVE_START_MINT_FEE_MODEL_ONLY",
                        "leg_index":i,"venue":row["venue"],
                        "pool":row["address"],"source_slot":source_slot,
                        "source_fee_lamports":fee["estimated_fee_lamports"],
                        "modeled_start_mint_fee_units":amount,
                        "protocol_exact_verified":False,
                        "conversion_is_guaranteed_upper_bound":False,
                        "paid_fee_verified":False,**SAFE}
            cost=amount
            reason=("source-native same-slot WSOL conversion MODEL; "
                    "fee and exchange rate are not paid or execution verified")
            break
    return {"status":"SIGNED_LOCAL_SIMULATION_ESTIMATED_NET_NOT_PROFIT_VERIFIED"
                      if cost is not None else "SIGNED_LOCAL_SIMULATION_START_MINT_COST_UNCONVERTED",
            "start_mint":start_mint,"source_slot":source_slot,
            "observed_local_fork_gross_delta_start_mint_base_units":gross,
            "estimated_cost_start_mint_base_units":cost,
            "estimated_net_delta_start_mint_base_units":gross-cost if cost is not None else None,
            "cost_reason":reason,
            "source_native_fee_conversion":conversion,
            "cost_conversion_protocol_exact_verified":False,
            "signed_local_simulation_succeeded":receipt.get("signed_atomic_simulation_verified") is True,
            "paid_network_fee_verified":False,"net_profit_verified":False,
            "protocol_exact_quote_verified":False,**SAFE}
