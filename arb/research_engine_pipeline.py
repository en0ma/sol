"""Sol's agreed operating pipeline: discover -> registry -> graph -> quote ->
risk -> atomic simulation -> evidence -> decision -> refresh.

This is an offline, dependency-injected orchestrator. Providers must supply
fresh authenticated pools/quotes and real signed simulation receipts. No RPC,
transaction broadcast, fabricated state or self-certified execution.
"""
from arb.opportunity_graph import cycles
from arb.opportunity_quote_pipeline import screen
from arb.next_ten_atomic_evidence import assess
from arb.market_state_registry import normalize

SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

def authenticated_registry(snapshot, *, now, max_age=60):
    """One canonical source/owner/slot authenticated registry across M5 paths."""
    normalized = normalize(snapshot, as_of_unix=now, max_age_seconds=max_age)
    return {"pools": normalized["pools"], "rejected": normalized["rejections"],
            "status": normalized["status"], "max_slot": normalized["max_slot"],
            **SAFETY}

def run_cycle_pipeline(snapshot, *, now, quote_provider, cost_provider,
                       simulate_provider=None, max_age=60, max_cycles=200,
                       initial_input=None):
    """Never infer signed proof from quote math; simulator must return receipts.

    Provider invocation is intentionally local/injected: this function cannot
    reach mainnet or sign transactions. Missing providers/results fail closed.
    """
    if type(now)is not int or now<0 or type(max_age)is not int or max_age<1:
        raise ValueError("invalid freshness policy")
    if initial_input is not None and (type(initial_input)is not int or not 0<initial_input<2**64):
        raise ValueError("invalid initial exact-input amount")
    if not callable(quote_provider) or not callable(cost_provider):
        raise ValueError("quote and cost providers required")
    registry=authenticated_registry(snapshot,now=now,max_age=max_age)
    graph=cycles(registry["pools"],max_cycles=max_cycles) if registry["pools"] else []
    rows=[]
    for route in graph:
        edges=[{"venue":leg["venue"],"pool":leg["pool"],
                "input_mint":leg["input"],"output_mint":leg["output"]}
               for leg in route["legs"]]
        candidate={"start_mint":route["start_mint"],"legs":edges}
        quotes=[];reason=None
        for leg in edges:
            try:
                q=quote_provider(leg,quotes[-1]["amount_out"] if quotes else initial_input)
                if not isinstance(q,dict) or any(q.get(k)!=leg[k] for k in leg):
                    raise ValueError("provider quote identity mismatch")
                if quotes and q.get("amount_in")!=quotes[-1].get("amount_out"):
                    raise ValueError("provider input does not consume quoted previous output")
                quotes.append(q)
            except (ValueError,KeyError,TypeError) as exc:
                reason="quote unavailable: "+str(exc)[:200]
                break
        if reason:
            rows.append({"route":candidate,"status":"UNASSESSABLE",
                         "reason_codes":[reason],**SAFETY})
            continue
        try:
            costs=cost_provider(candidate,quotes)
            evaluation=screen(candidate,quotes,costs,now=now,max_age=max_age)
        except (ValueError,KeyError,TypeError) as exc:
            evaluation={"status":"UNASSESSABLE","reason_codes":["research screening failed: "+str(exc)[:200]],
                        "conservative_net_start_mint_units":None,**SAFETY}
        result={"route":candidate,"research":evaluation,"status":evaluation["status"],
                "signed_simulation_verified":False,**SAFETY}
        if evaluation.get("status")=="RESEARCH_CANDIDATE_ONLY" and evaluation.get("positive_after_declared_costs"):
            # Distinct research and execution evidence: direct receipt must pass
            # the existing signed two-instruction assessor to qualify as proof.
            if len(edges)==2 and edges[0]["venue"]!=edges[1]["venue"] and callable(simulate_provider):
                receipt=simulate_provider(candidate,quotes)
                proof=assess((edges[0]["venue"],edges[1]["venue"]),receipt)
                result["simulation_audit"]=proof
                result["signed_simulation_verified"]=proof["status"]=="VERIFIED"
            else:
                result["simulation_audit"]={"status":"UNVERIFIED",
                    "failure_reasons":["signed simulator unavailable or route not two distinct venues"]}
        rows.append(result)
    return {"status":"RESEARCH_ONLY","initial_input_base_units":initial_input,"authenticated_pools":len(registry["pools"]),
            "rejected_pools":registry["rejected"],"graph_cycles":len(graph),
            "screened_routes":len(rows),"research_positive":sum(
                x.get("research",{}).get("positive_after_declared_costs") is True for x in rows),
            "signed_simulated_candidates":sum(x.get("signed_simulation_verified") is True for x in rows),
            "results":rows,"execution_decision":"DISABLED",**SAFETY}
