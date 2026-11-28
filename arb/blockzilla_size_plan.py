"""Bounded source-native size selection before signed simulation.

Reuse the existing seven-venue route chain. Every trial is bound to the
same captured fixture; no signed result is used to select its input.
This is a discrete research grid, not a continuous optimizer or profit claim.
"""
from arb.source_snapshot_manifest import verify
from arb.m5_source_indicative_route_chain import research_chain
from arb.m5_signed_start_mint_economics import WSOL

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
CONTROL_AMOUNTS=(100000,1000000)
GRID=(10000,30000,100000,300000,1000000,3000000,10000000,30000000)
# A fixed research assumption, not a paid or independently quoted fee.
MESSAGE_FEE_SCENARIO=5000
MAX_EXTRA_PER_ROUTE=2
COMPLETE={"SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED",
          "SOURCE_BOUND_MODELED_CHAIN_NOT_EXECUTION_VERIFIED"}

def evaluate(fixture,*,observed_unix):
    verify(fixture)
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe source size fixture")
    mints=fixture.get("route_mints")
    if not isinstance(mints,list) or not 4<=len(mints)<=7 or mints[0]!=mints[-1]:
        raise ValueError("closed 3–6-hop size fixture required")
    if type(observed_unix) is not int or observed_unix<0:
        raise ValueError("source clock required")
    results=[]
    for amount in GRID:
        row={"amount":amount,"status":"MODEL_BLOCKED","output":None,
             "gross_delta":None,"estimated_message_fee":None,"estimated_net":None,
             "net_profit_verified":False,**SAFE}
        try:
            q=research_chain(fixture,amount_in=amount,observed_unix=observed_unix,
                             allow_modeled_dlmm=True,allow_modeled_pumpswap=True)
        except (ValueError,RuntimeError,TypeError,KeyError) as exc:
            row["reason"]=str(exc)[:180]
            results.append(row)
            continue
        if not isinstance(q,dict) or any(q.get(k) is not False for k in SAFE):
            raise ValueError("unsafe native size model")
        row["quote_status"]=q.get("status")
        if q["status"] in COMPLETE:
            output=q.get("output_base_units")
            if (q.get("input_base_units")!=amount or type(output) is not int or not 0<output<2**64
                    or q.get("gross_delta_start_mint_base_units")!=output-amount
                    or q.get("signed_simulation_verified") is not False
                    or q.get("net_profit_verified") is not False
                    or len(q.get("quoted_legs",[]))!=len(mints)-1):
                raise ValueError("invalid complete size model")
            fee=MESSAGE_FEE_SCENARIO if mints[0]==WSOL else None
            row.update(status="COMPLETE_RESEARCH_MODEL",output=output,gross_delta=output-amount,
                       estimated_message_fee=fee,estimated_net=output-amount-fee if fee is not None else None,
                       modeled_leg_count=q.get("modeled_leg_count"))
        else:
            row.update(blocked_leg=q.get("blocked_leg_index"),blocked_venue=q.get("blocked_venue"),
                       reason=q.get("reason"))
        results.append(row)
    selected=select_sizes(results)
    return {"status":"SOURCE_NATIVE_BOUNDED_SIZE_PLAN","source_slot":fixture["state_accounts_observed_slot"],
            "manifest_sha256":fixture["state_account_manifest_sha256"],"source_unix":observed_unix,
            "start_mint":mints[0],"grid":list(GRID),"controls":list(CONTROL_AMOUNTS),
            "samples":results,"selected":selected,"signed_amounts":list(CONTROL_AMOUNTS)+[r["amount"] for r in selected],
            "complete_models":sum(r["status"]=="COMPLETE_RESEARCH_MODEL" for r in results),
            "positive_modeled_gross_count":sum(type(r["gross_delta"]) is int and r["gross_delta"]>0 for r in results),
            "positive_estimated_net_count":sum(type(r["estimated_net"]) is int and r["estimated_net"]>0 for r in results),
            "grid_exhaustive_only":True,"priority_cost_included":False,"account_funding_included":False,
            "net_profit_verified":False,**SAFE}

def select_sizes(samples):
    if [r.get("amount") for r in samples]!=list(GRID):
        raise ValueError("size grid must be complete and ordered")
    eligible=[r for r in samples if r.get("status")=="COMPLETE_RESEARCH_MODEL"
              and r["amount"] not in CONTROL_AMOUNTS]
    if not eligible:
        return []
    # A best estimated net candidate plus the largest complete candidate
    # independently stress economic and liquidity boundaries. Never select
    # a blocked model or use realized output for ranking.
    def score(r):
        net=r.get("estimated_net")
        return (net if type(net) is int else r["gross_delta"],-r["amount"])
    best=max(eligible,key=score)
    largest=max(eligible,key=lambda r:r["amount"])
    out=[{"amount":best["amount"],"reason":"BEST_MODELED_NET_OR_GROSS_GRID_SAMPLE"}]
    if largest["amount"]!=best["amount"]:
        out.append({"amount":largest["amount"],"reason":"LARGEST_COMPLETE_GRID_SAMPLE"})
    return out

def verify_plan(recorded,fixture,*,observed_unix):
    recomputed=evaluate(fixture,observed_unix=observed_unix)
    if recorded!=recomputed:
        raise ValueError("recorded pre-sign size plan differs from independent recomputation")
    return recomputed


def rank_comparable_grid(plans):
    """Compare complete models only at equal input amount and denomination.

    Source fixtures are independently captured at potentially different slots.
    Rankings are historical research comparisons, not simultaneous prices.
    A non-WSOL group has no modeled message-fee conversion; rank gross only.
    """
    from collections import defaultdict
    groups=defaultdict(list)
    for rid,plan in sorted(plans.items()):
        if (not isinstance(rid,str) or plan.get("status")!="SOURCE_NATIVE_BOUNDED_SIZE_PLAN"
                or any(plan.get(k) is not False for k in SAFE)
                or [s.get("amount") for s in plan.get("samples",[])]!=list(GRID)):
            raise ValueError("invalid complete comparable size plan")
        mint=plan.get("start_mint")
        if not isinstance(mint,str) or not mint or type(plan.get("source_slot")) is not int:
            raise ValueError("size plan source identity missing")
        for sample in plan["samples"]:
            if sample.get("status")!="COMPLETE_RESEARCH_MODEL":
                continue
            amount=sample["amount"];gross=sample.get("gross_delta")
            net=sample.get("estimated_net")
            if (type(gross) is not int or sample.get("output")!=amount+gross
                    or (mint==WSOL and (sample.get("estimated_message_fee")!=MESSAGE_FEE_SCENARIO
                                        or net!=gross-MESSAGE_FEE_SCENARIO))
                    or (mint!=WSOL and (net is not None or sample.get("estimated_message_fee") is not None))):
                raise ValueError("size grid economic identity mismatch")
            groups[(mint,amount)].append({"id":rid,"source_slot":plan["source_slot"],
                "gross_delta":gross,"estimated_net":net,
                "selected_for_signing":amount in plan["signed_amounts"],
                "net_profit_verified":False,**SAFE})
    result=[]
    for (mint,amount),rows in sorted(groups.items()):
        ordered=sorted(rows,key=lambda r:(-(r["estimated_net"] if mint==WSOL else r["gross_delta"]),r["id"]))
        slots=[r["source_slot"] for r in ordered]
        result.append({"start_mint":mint,"amount":amount,"rank_by":"ESTIMATED_MESSAGE_FEE_NET" if mint==WSOL else "GROSS_ONLY",
            "source_slot_range":[min(slots),max(slots)],"simultaneous_source_snapshot":False,
            "status":"PRE_SIGN_RESEARCH_COMPARISON_ONLY","routes":ordered,
            "priority_cost_included":False,"account_funding_included":False,
            "net_profit_verified":False,**SAFE})
    return result


def select_priced_six_hop_sources(rows, plans, *, cap=2):
    """Choose among captured six-hop alternatives before any signed execution.

    Footprint class dominates pricing coverage; controls and completed grid
    samples determine preference within a class. Neither missing models nor
    an oversized estimate is treated as an observed runtime rejection.
    """
    from arb.blockzilla_source_footprint import PREFERRED_KEYS, select_six_hop_sources
    baseline=select_six_hop_sources(rows,cap=cap)
    ids={row["id"] for row in rows}
    if set(plans)!=ids:
        raise ValueError("six-hop pricing candidate coverage mismatch")
    ranked=[]
    for index,row in enumerate(rows):
        rid=row["id"]
        footprint=row["source_account_footprint"]
        plan=plans[rid]
        if (plan.get("status")!="SOURCE_NATIVE_BOUNDED_SIZE_PLAN"
                or plan.get("source_slot")!=row["source_slot"]
                or plan.get("manifest_sha256")!=footprint["manifest_sha256"]
                or plan.get("source_unix")!=row["source_clock"]["unix_timestamp"]
                or plan.get("start_mint")!=row["start_mint"]
                or any(plan.get(k) is not False for k in SAFE)
                or plan.get("net_profit_verified") is not False
                or [s.get("amount") for s in plan.get("samples",[])]!=list(GRID)):
            raise ValueError("six-hop pricing plan source identity mismatch")
        rank_comparable_grid({rid:plan})
        complete=[s["amount"] for s in plan["samples"]
                  if s["status"]=="COMPLETE_RESEARCH_MODEL"]
        if (len(complete)!=plan.get("complete_models")
                or plan.get("selected")!=select_sizes(plan["samples"])
                or plan.get("signed_amounts")!=list(CONTROL_AMOUNTS)+[
                    s["amount"] for s in plan["selected"]]):
            raise ValueError("six-hop pricing plan size coverage mismatch")
        controls=sum(amount in complete for amount in CONTROL_AMOUNTS)
        keys=footprint["resolved_account_key_estimate"]
        group=1 if keys is None else 0 if keys<=PREFERRED_KEYS else 2
        # Do not compare raw economic values across different mints/sizes.
        # Larger footprints remain last; prefer fewer keys within that class.
        priority=(group,keys if group==2 else 0,-controls,-len(complete),index)
        ranked.append((priority,{"id":rid,"resolved_account_key_estimate":keys,
            "complete_control_models":controls,"complete_grid_models":len(complete),
            "source_slot":plan["source_slot"],"source_unix":plan["source_unix"],
            "manifest_sha256":plan["manifest_sha256"],"start_mint":plan["start_mint"],
            "footprint_priority_class":group,**SAFE}))
    candidates=[row for _,row in sorted(ranked,key=lambda item:item[0])]
    chosen=[row["id"] for row in candidates[:cap]]
    return {"status":"PRE_SIGN_SOURCE_PRICING_AND_FOOTPRINT_SELECTION",
            "footprint_only_ids":baseline,"selected_ids":chosen,
            "candidates":[{**row,"selected":row["id"] in chosen} for row in candidates],
            "signed_results_used":False,"simultaneous_source_snapshot":False,
            "net_profit_verified":False,**SAFE}
