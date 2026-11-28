"""Compute source-mint net SOL economics from actual signed local-fork results.

Transaction fee remains a signed-message RPC estimate, not a paid mainnet fee.
Only wrapped native SOL starting mint admits a direct lamport conversion. SPL
start-mint costs require an independently authenticated conversion quote.
"""
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
WSOL="So11111111111111111111111111111111111111112"

def source_native_fee_conversion(fixture,*,start_mint,source_slot,fee_lamports,observed_unix):
    """Model a fee-denominated exact-input conversion on the captured forward path.

    This common implementation serves assumed pre-sign costs and recorded
    signed-message estimates. Neither use represents a paid fee or a guaranteed
    acquisition cost; no reverse or different-slot pool is inferred.
    """
    if (not isinstance(fixture,dict) or type(start_mint) is not str
            or type(source_slot) is not int or source_slot<0
            or type(fee_lamports) is not int or not 0<fee_lamports<2**64
            or type(observed_unix) is not int or observed_unix<0):
        raise ValueError("invalid source-native fee conversion inputs")
    conversion=cost=None
    reason="no supported same-source forward WSOL conversion"
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
    from arb.m5_source_indicative_route_chain import source_model_output
    supported=frozenset(("orca","raydium_clmm","raydium_cpmm",
                         "raydium_amm_v4","meteora_damm_v2","meteora_dlmm",
                         "pumpswap"))

    def conversion_output(index,amount,q):
        row=rows[index]
        if (not isinstance(q,dict) or
                any(q.get(k) is not False for k in SAFE) or
                q.get("source_slot")!=source_slot or
                q.get("venue")!=row["venue"] or q.get("pool")!=row["address"]):
            raise ValueError("non-authenticated fee conversion quote")
        status,output,modeled=source_model_output(
            fixture,row,index,amount,observed_unix,q,
            allow_modeled_dlmm=True,allow_modeled_pumpswap=True)
        if ((status!="SOURCE_BOUND_INDICATIVE" and not modeled)
                or type(output) is not int or not 0<output<2**64):
            return None,status,False
        return output,status,modeled
    for i,row in enumerate(rows):
        if (row["venue"] not in supported or
                mints[i]!=WSOL or mints[i+1]!=start_mint):
            continue
        q=quote_leg(fixture,leg_index=i,
                    amount_in=fee_lamports,
                    observed_unix=observed_unix)
        amount,status,modeled=conversion_output(i,fee_lamports,q)
        if amount is None:
            continue
        conversion={"status":"SOURCE_NATIVE_START_MINT_FEE_MODEL_ONLY",
                    "leg_index":i,"venue":row["venue"],
                    "pool":row["address"],"source_slot":source_slot,
                    "source_fee_lamports":fee_lamports,
                    "modeled_start_mint_fee_units":amount,
                    "quote_status":status,
                    "uses_unverified_dynamic_fee_model":modeled,
                    "protocol_exact_verified":False,
                    "conversion_is_guaranteed_upper_bound":False,
                    "paid_fee_verified":False,**SAFE}
        cost=amount
        reason=("source-native same-slot WSOL conversion MODEL; "
                "fee and exchange rate are not paid or execution verified")
        break
    if conversion is None and mints[-1]==start_mint:
        # Only use the forward suffix of the same captured directed route.
        # Reversing a leg would lack its directional account evidence.
        for first in range(len(rows)-2,-1,-1):
            if mints[first]!=WSOL or len(rows)-first>5:
                continue
            if any(r["venue"] not in supported for r in rows[first:]):
                continue
            current=fee_lamports
            trace=[]
            for i in range(first,len(rows)):
                row=rows[i]
                q=quote_leg(fixture,leg_index=i,amount_in=current,
                            observed_unix=observed_unix)
                output,status,modeled=conversion_output(i,current,q)
                if output is None:
                    break
                trace.append({"leg_index":i,"venue":row["venue"],"pool":row["address"],
                    "input_mint":mints[i],"output_mint":mints[i+1],
                    "input_base_units":current,"output_base_units":output,"source_slot":source_slot,
                    "quote_status":status,"uses_unverified_dynamic_fee_model":modeled})
                current=output
            if len(trace)!=len(rows)-first:
                continue
            conversion={"status":"SOURCE_NATIVE_MULTILEG_START_MINT_FEE_MODEL_ONLY",
                "source_slot":source_slot,"source_fee_lamports":fee_lamports,
                "modeled_start_mint_fee_units":current,"conversion_legs":trace,
                "uses_unverified_dynamic_fee_model":any(
                    leg["uses_unverified_dynamic_fee_model"] for leg in trace),
                "protocol_exact_verified":False,"conversion_is_guaranteed_upper_bound":False,
                "paid_fee_verified":False,**SAFE}
            cost=current
            reason="same-source forward WSOL conversion chain MODEL; fee and exchange rate not paid or execution verified"
            break
    return cost,conversion,reason


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
        cost,conversion,reason=source_native_fee_conversion(fixture,start_mint=start_mint,
            source_slot=source_slot,fee_lamports=fee["estimated_fee_lamports"],
            observed_unix=observed_unix)
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


def compact_primary_economic_evidence(entry):
    """Export independently checked gross/cost evidence without large traces."""
    audit=entry["audit"]
    if any(audit.get(k) is not False for k in SAFE):
        raise ValueError("unsafe primary signed audit")
    amount=entry["amount"];post=audit["positive_post_balances"]
    if (type(amount) is not int or not 0<amount<2**64 or not isinstance(post,list)
            or len(post)!=4 or any(type(x) is not int or not 0<=x<2**64 for x in post)
            or audit["planned_inputs"][0]!=amount):
        raise ValueError("primary economic audit amount mismatch")
    gross=post[-1]-amount
    signed=audit.get("signed_economics")
    source=audit.get("source_economic_model")
    cost=net=model_output=model_gross=model_net=None
    if signed is not None:
        if (any(signed.get(k) is not False for k in SAFE)
                or signed.get("net_profit_verified") is not False
                or signed.get("paid_network_fee_verified") is not False
                or signed.get("start_mint")!=entry["start_mint"]
                or signed.get("source_slot")!=entry["source_slot"]
                or signed.get("observed_local_fork_gross_delta_start_mint_base_units")!=gross):
            raise ValueError("primary signed economics identity mismatch")
        cost=signed.get("estimated_cost_start_mint_base_units")
        net=signed.get("estimated_net_delta_start_mint_base_units")
        if (cost is None and net is not None or cost is not None and
                (type(cost) is not int or cost<0 or type(net) is not int or net!=gross-cost)):
            raise ValueError("primary signed estimated net mismatch")
    if source is not None:
        if (any(source.get(k) is not False for k in SAFE)
                or source.get("net_profit_verified") is not False
                or source.get("start_mint")!=entry["start_mint"]
                or source.get("source_slot")!=entry["source_slot"]
                or source.get("input_base_units")!=amount):
            raise ValueError("primary source economics identity mismatch")
        model_output=source.get("output_base_units")
        model_gross=source.get("gross_delta");model_net=source.get("estimated_net_delta")
        if model_output is not None:
            if (type(model_output) is not int or not 0<model_output<2**64
                    or model_gross!=model_output-amount or source.get("status")!="PRIMARY_SOURCE_ECONOMIC_MODEL_ONLY"
                    or (model_net is not None and (
                        type(source.get("estimated_message_fee_base_units")) is not int
                        or source["estimated_message_fee_base_units"]<0
                        or type(model_net) is not int
                        or model_net!=model_gross-source["estimated_message_fee_base_units"]))):
                raise ValueError("primary model economic arithmetic mismatch")
        elif model_gross is not None or model_net is not None:
            raise ValueError("blocked primary model contains economic result")
        if model_net is not None and entry["start_mint"]!=WSOL:
            conversion=source.get("source_native_fee_conversion")
            if (not isinstance(conversion,dict) or any(conversion.get(k) is not False for k in SAFE)
                    or conversion.get("source_slot")!=entry["source_slot"]
                    or conversion.get("source_fee_lamports")!=source.get("message_fee_scenario_lamports")
                    or conversion.get("modeled_start_mint_fee_units")!=source["estimated_message_fee_base_units"]
                    or conversion.get("paid_fee_verified") is not False
                    or conversion.get("protocol_exact_verified") is not False):
                raise ValueError("unbound primary source fee conversion model")
    return {"id":entry["id"],"start_mint":entry["start_mint"],"source_slot":entry["source_slot"],
        "fixture_sha256":entry["fixture_sha256"],"receipt_sha256":entry["receipt_sha256"],
        "amount":amount,"terminal":post[-1],"observed_gross":gross,"estimated_cost":cost,
        "estimated_net":net,"modeled_output":model_output,"modeled_gross":model_gross,
        "modeled_net":model_net,
        "modeled_cost":source.get("estimated_message_fee_base_units") if source else None,
        "source_model_status":source.get("status") if source else None,
        "source_model_matches_terminal":model_output==post[-1] if model_output is not None else None,
        "net_profit_verified":False,**SAFE}


def rank_primary_economic_evidence(rows,*,expected_ids):
    """Rank comparable signed controls only; never aggregate token units across mints."""
    from collections import defaultdict
    if (not isinstance(rows,list) or len(rows)!=len(expected_ids)
            or len({r["id"] for r in rows})!=len(rows)
            or {r["id"] for r in rows}!=set(expected_ids)):
        raise ValueError("primary economic evidence coverage mismatch")
    groups=defaultdict(list)
    for r in rows:
        if (any(r.get(k) is not False for k in SAFE) or r.get("net_profit_verified") is not False
                or not isinstance(r.get("start_mint"),str) or not r["start_mint"]
                or type(r.get("source_slot")) is not int or r["source_slot"]<0
                or any(type(r.get(k)) is not int for k in ("amount","terminal","observed_gross"))
                or not 0<r["amount"]<2**64 or not 0<r["terminal"]<2**64
                or r["observed_gross"]!=r["terminal"]-r["amount"]):
            raise ValueError("invalid primary economic evidence")
        cost=r["estimated_cost"];net=r["estimated_net"]
        if (cost is None and net is not None or cost is not None and
                (type(cost) is not int or cost<0 or type(net) is not int or net!=r["observed_gross"]-cost)):
            raise ValueError("primary economic evidence net mismatch")
        output=r["modeled_output"]
        if (output is None and (r["modeled_gross"] is not None or r["modeled_net"] is not None
                or r["source_model_matches_terminal"] is not None)
                or output is not None and (type(output) is not int or not 0<output<2**64
                or r["modeled_gross"]!=output-r["amount"]
                or r["source_model_matches_terminal"] is not (output==r["terminal"]))):
            raise ValueError("primary economic model output mismatch")
        model_cost=r.get("modeled_cost")
        if (model_cost is None and r["modeled_net"] is not None or model_cost is not None and
                (type(model_cost) is not int or model_cost<0 or type(r["modeled_net"]) is not int
                 or output is None or r["modeled_net"]!=r["modeled_gross"]-model_cost)):
            raise ValueError("primary modeled estimated net mismatch")
        groups[(r["start_mint"],r["amount"])].append(r)
    comparisons=[]
    for (mint,amount),items in sorted(groups.items()):
        gross=sorted(items,key=lambda r:(-r["observed_gross"],r["id"]))
        net=sorted((r for r in items if r["estimated_net"] is not None),
                   key=lambda r:(-r["estimated_net"],r["id"]))
        modeled=sorted((r for r in items if r["modeled_gross"] is not None),
                   key=lambda r:(-r["modeled_gross"],r["id"]))
        modeled_net=sorted((r for r in items if r["modeled_net"] is not None),
                           key=lambda r:(-r["modeled_net"],r["id"]))
        slots=[r["source_slot"] for r in items]
        comparisons.append({"start_mint":mint,"amount":amount,"source_slot_range":[min(slots),max(slots)],
            "gross_ranked_ids":[r["id"] for r in gross],"estimated_net_ranked_ids":[r["id"] for r in net],
            "modeled_gross_ranked_ids":[r["id"] for r in modeled],
            "modeled_net_ranked_ids":[r["id"] for r in modeled_net],
            "net_unconverted_ids":[r["id"] for r in gross if r["estimated_net"] is None],
            "simultaneous_source_snapshot":False,"net_profit_verified":False,**SAFE})
    return {"status":"PRIMARY_ACCEPTED_ROUTE_ECONOMIC_RESEARCH_ONLY",
        "accepted_route_count":len(rows),"comparable_group_count":len(comparisons),
        "complete_source_models":sum(r["modeled_output"] is not None for r in rows),
        "complete_source_cost_models":sum(r["modeled_net"] is not None for r in rows),
        "positive_modeled_net_count":sum(r["modeled_net"] is not None and r["modeled_net"]>0 for r in rows),
        "source_terminal_matches":sum(r["source_model_matches_terminal"] is True for r in rows),
        "positive_observed_gross_count":sum(r["observed_gross"]>0 for r in rows),
        "estimated_cost_converted_count":sum(r["estimated_cost"] is not None for r in rows),
        "positive_estimated_net_count":sum(r["estimated_net"] is not None and r["estimated_net"]>0 for r in rows),
        "unconverted_cost_count":sum(r["estimated_cost"] is None for r in rows),
        "groups":comparisons,"routes":sorted(rows,key=lambda r:r["id"]),
        "priority_cost_fully_verified":False,"paid_network_fee_verified":False,
        "net_profit_verified":False,**SAFE}
