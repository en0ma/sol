"""Bounded empirical graph-selected three-hop build and simulate inventory.

Source phase on read-only upstream fork; offline phase after destroying source
fork. Never mark a discovered edge as a signed packet or simulated swap.
"""
import argparse
import json
from pathlib import Path

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def choose_pool_diverse_candidate(queue, selected_identities, used_pools, *,
                                  start_used_pools=None, window=256):
    """Pick a fresh route maximizing pool coverage within a bounded queue window.

    Retain start-token round robin; do not treat candidate discovery as execution.
    """
    eligible=[(i,identity,route) for i,(identity,route) in enumerate(queue)
              if identity not in selected_identities]
    if not eligible:
        return None
    # Look past the lexicographically earliest 3-hop combinations, which can
    # repeatedly sample the same large pool cluster.
    if start_used_pools is None:
        start_used_pools=set()
    def score(item):
        index,identity,route=item
        pools={(leg["venue"],leg["pool"]) for leg in route["legs"]}
        # A distinct starting mint needs independently capturable pool
        # alternatives. Global novelty alone can repeatedly choose the same
        # unusable pool for a mint's second and third route rotations.
        return (len(pools-start_used_pools),len(pools-used_pools),
                len(pools),-index)
    position,identity,route=max(eligible[:window],key=score)
    del queue[position]
    return identity,route

def failed_instruction_context(row, error):
    """Identify the failed top-level swap leg without guessing a DEX error meaning."""
    import re
    if not isinstance(error,str):
        return {}
    match=re.search(r"InstructionError.*?\[\s*(\d+)\s*,\s*\{.*?Custom.*?:\s*(\d+)\s*\}",error)
    if not match:
        return {}
    index,code=map(int,match.groups())
    venues=row.get("venues",[])
    pools=row.get("pools",[])
    if index>=len(venues) or index>=len(pools):
        return {"failed_instruction_index":index,"program_error_code":code}
    result={"failed_instruction_index":index,"program_error_code":code,
            "failed_venue":venues[index],"failed_pool":pools[index]}
    if venues[index]=="meteora_dlmm" and code==6042:
        result["program_error_name"]="PoolDisabled"
        result["diagnostic_class"]="DLMM_SWAP_BLOCKED_BY_POOL_STATUS_OR_ACTIVATION"
    elif venues[index]=="meteora_dlmm" and code==6036:
        result["program_error_name"]="BitmapExtensionAccountIsNotProvided"
        result["diagnostic_class"]="DLMM_BITMAP_EXTENSION_ACCOUNT_MISSING"
    elif venues[index]=="meteora_damm_v2" and code==6002:
        result["program_error_name"]="ExceededSlippage"
        result["diagnostic_class"]="DAMM_V2_SIGNED_SLIPPAGE_REJECTION"
    elif venues[index]=="raydium_clmm" and code==6024:
        result["program_error_name"]="InvalidFirstTickArrayAccount"
        result["diagnostic_class"]="CLMM_FIRST_INITIALIZED_TICK_ARRAY_MISMATCH"
    return result

def diversified_three_hop_graph(readiness, maximum=100, *,
                                allow_start_rotations=False):
    """Bounded round-robin across authenticated token cycles and pool identities."""
    from collections import defaultdict, deque
    from arb.m5_seven_venue_route_scan import analyze, ORDER, SAFE
    from arb.opportunity_graph import cycles
    if type(maximum)is not int or not 1<=maximum<=200:
        raise ValueError("invalid cycle budget")
    if type(allow_start_rotations) is not bool:
        raise ValueError("invalid start-token rotation policy")
    pools=[{"venue":v,"address":p["pool"],"mints":p["mints"],"verified":True}
           for v in ORDER for p in readiness["authenticated_pools"][v]]
    graph=analyze(readiness,max_cycles=100)
    # Keep rotations as alternative start-token choices for each genuine pool
    # cycle. Select one unique pool cycle per round-robin starting token.
    candidates=defaultdict(deque)
    seen_by_start=defaultdict(set)
    unique_identities=set()
    for anchor in sorted({m for p in pools for m in p["mints"]}):
        for route in cycles(pools,anchors=[anchor],min_hops=3,max_hops=3,
                            max_cycles=1000,truncate=True):
            legs=route["legs"]
            keys=tuple((x["venue"],x["pool"],x["input"]) for x in legs)
            identity=min(keys[i:]+keys[:i] for i in range(3))
            unique_identities.add(identity)
            if identity in seen_by_start[anchor]:
                continue
            seen_by_start[anchor].add(identity)
            candidates[anchor].append((identity,route))
    result=[]
    selected_identities=set()
    used_pools=set()
    used_pools_by_start=defaultdict(set)
    starts=sorted(candidates)
    while starts and len(result)<maximum:
        next_starts=[]
        for start in starts:
            q=candidates[start]
            # Distinct token starting balances make a rotation an independent
            # signed route, even when underlying pool cycle is shared. Keep
            # canonical pool-cycle de-dup within each anchor, but allow
            # alternate source mints to prove their own signed execution.
            scoped_seen=({identity for anchor,identity in selected_identities
                          if anchor==start} if allow_start_rotations
                          else selected_identities)
            choice=choose_pool_diverse_candidate(
                q,scoped_seen,used_pools,
                start_used_pools=used_pools_by_start[start])
            if choice is not None:
                identity,r=choice
                selected_identities.add((start,identity) if allow_start_rotations else identity)
                selected_route_pools={(leg["venue"],leg["pool"]) for leg in r["legs"]}
                used_pools.update(selected_route_pools)
                used_pools_by_start[start].update(selected_route_pools)
                result.append({"start_mint":r["start_mint"],"hops":3,
                    "legs":r["legs"],"venue_count":len(r["venues"]),
                    "quote_status":"NOT_QUOTED",
                    "signed_simulation_status":"NOT_ATTEMPTED",**SAFE})
            if any(((start,identity) if allow_start_rotations else identity)
                   not in selected_identities for identity,_ in q):
                next_starts.append(start)
            if len(result)>=maximum:
                break
        starts=next_starts
    if not result:
        raise ValueError("no authenticated triangles found")
    graph.update(routes=result,connected_cycles=len(result),
        cycle_budget=maximum,cycle_inventory_truncated=True,
        cycle_count_is_exhaustive=False,
        source_swap_eligibility_rejections=readiness.get("source_swap_eligibility_rejections",[]),
        source_swap_eligibility_rejection_count=len(readiness.get("source_swap_eligibility_rejections",[])),
        three_hop_candidate_identities_considered=len(unique_identities),
        three_hop_distinct_token_paths=len({tuple([r["start_mint"]]+[leg["output"] for leg in r["legs"][:2]]) for r in result}),
        three_hop_distinct_start_mints=len({r["start_mint"] for r in result}),
        three_hop_distinct_selected_pools=len(used_pools),
        three_hop_distinct_selected_venues=len({v for v,_ in used_pools}),
        three_hop_sample_policy=("START_MINT_ROUND_ROBIN_PER_START_POOL_NOVELTY_256_ROTATIONS" if allow_start_rotations else
                                 "START_MINT_ROUND_ROBIN_PER_START_POOL_NOVELTY_256_ROTATION_DEDUP"),
        cycle_coverage_by_hops={"3":{"returned":len(result),
            "budget":maximum,"truncated":len(unique_identities)>len(result)}})
    return graph

def capture_priority_indices(routes, *, retries_per_start=3):
    """Schedule scarce mint starts before route-volume fill.

    Order one distinct candidate for each mint, then retry up to two
    alternatives for still-uncaptured mints before assigning remaining
    source capture budget. This is only ordering, never authentication.
    """
    from collections import defaultdict
    by_start=defaultdict(list)
    for index,route in enumerate(routes):
        if route.get("hops")==3:
            by_start[route["start_mint"]].append(index)
    # Keep deterministic mint-level first appearance. Within a mint only,
    # favor an *exact* previously signed+rollback-verified route identity
    # as a source-capture hypothesis. The historical record is NOT a current
    # source authentication or an accepted signed verification.
    starts=sorted(by_start,key=lambda mint:by_start[mint][0])
    from arb.m5_historical_capture_priority import is_historical_priority
    for mint in starts:
        indices=by_start[mint]
        preferred=[i for i in indices
                   if is_historical_priority(routes[i])]
        if preferred:
            preferred_indices=set(preferred)
            others=[i for i in indices if i not in preferred_indices]
            by_start[mint]=preferred+others
    return by_start,starts


def capture_attempt_order(routes, by_start, starts, captured_starts, attempted, *,
                          retries_per_start=3):
    """Return a next untried route; reserve fresh starts before duplicates."""
    for depth in range(retries_per_start):
        for mint in starts:
            if mint in captured_starts:
                continue
            indices=by_start[mint]
            earlier=[routes[i] for i in indices if i in attempted]
            if depth==0:
                # First pass always covers every distinct starting token.
                if indices and indices[0] not in attempted:
                    return indices[0]
                continue
            # Later retries should test independent source-account hypotheses
            # before rotating the same failing pool direction. Direction
            # matters for Orca tick arrays and DLMM bin array source reads.
            if len(earlier)!=depth:
                continue
            seen={(leg["venue"],leg["pool"],leg.get("input"),
                   leg.get("output"))
                  for route in earlier for leg in route["legs"]}
            options=[]
            for i in indices:
                if i in attempted:
                    continue
                fresh=sum((leg["venue"],leg["pool"],leg.get("input"),
                           leg.get("output")) not in seen
                          for leg in routes[i]["legs"])
                if fresh:
                    options.append((fresh,i))
            if options:
                # Preserve source graph order for equally novel alternatives.
                return max(options,key=lambda x:(x[0],-x[1]))[1]
            # If genuine alternatives are absent, still try a different
            # route; never treat a repeated pool as proven unavailable.
            fallback=next((i for i in indices if i not in attempted),None)
            if fallback is not None:
                return fallback
    # Preserve a fourth (or later) independent pool-path attempt for
    # still-uncaptured starting mints before assigning any remaining capacity
    # to starts already captured. Routes that merely permute the same pool
    # set (e.g. the two blocked all-DLMM triangles) do not become a new
    # source-liquidity hypothesis: they were already attempted in the first
    # three mint-priority rounds.
    for mint in starts:
        if mint in captured_starts:
            continue
        earlier=[routes[i] for i in by_start[mint] if i in attempted]
        previously_seen={(leg["venue"],leg["pool"])
                         for route in earlier for leg in route["legs"]}
        for index in by_start[mint]:
            if index in attempted:
                continue
            identities={(leg["venue"],leg["pool"])
                        for leg in routes[index]["legs"]}
            if identities-previously_seen:
                return index
    # After giving every mint three attempts and fresh unserved pool paths,
    # promote a genuine reverse orientation before redundant fill.
    # A pool with exhausted A->B liquidity can still have source-verifiable
    # B->A tick arrays. The alternative must pass its OWN capture and later
    # signed simulation; topology alone never counts as proof.
    # A pool with exhausted A->B liquidity can still have source-verifiable
    # B->A tick arrays. The alternative must pass its OWN capture and later
    # signed simulation; topology alone never counts as proof.
    if captured_starts:
        for mint in starts:
            if mint not in captured_starts:
                continue
            seen={(routes[i]["legs"][0]["venue"],
                   routes[i]["legs"][-1]["venue"])
                  for i in attempted if routes[i].get("start_mint")==mint}
            for index in by_start[mint]:
                if index in attempted:
                    continue
                route=routes[index]
                direction=(route["legs"][0]["venue"],
                           route["legs"][-1]["venue"])
                if (direction not in seen and direction[1]=="orca"
                        and ("orca",direction[0]) in seen):
                    return index
    for index,route in enumerate(routes):
        if route.get("hops")==3 and index not in attempted:
            return index
    return None

def source_cliff_hints(fixture):
    """Fresh direction-specific observations, never signed rejection verdicts.

    Only an authenticated first downward initialized tick with zero
    remaining liquidity and no lower initialized ticks in the three
    captured arrays qualifies. Do not infer a cliff on the reverse swap.
    The first captured route per start mint remains in the primary sample.
    """
    from arb.whirlpool_ticks import authenticated_downward_liquidity_cliff
    hints=[]
    errors=[]
    for i,venue in enumerate(fixture.get("route_venues",[])):
        if venue!="orca":
            continue
        try:
            observation=authenticated_downward_liquidity_cliff(fixture,i)
            if (isinstance(observation,dict) and
                    observation.get("status")=="SOURCE_AUTHENTICATED_FIRST_DOWNWARD_TICK_DEPLETES_LIQUIDITY" and
                    observation.get("liquidity_after_first_crossing")=="0" and
                    observation.get("additional_initialized_ticks_below_in_three_arrays")==0 and
                    all(observation.get(k) is False for k in SAFE)):
                hints.append({"leg_index":i,**observation})
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            errors.append({"leg_index":i,"error_class":type(exc).__name__})
    return hints,errors


def capture_selection(rows,deferred,*,target):
    """Retain exact primary count using authenticated fallback fixtures.

    Deferred rows were captured, not rejected or signed. Restore them in
    original order only when other source candidates cannot fill target.
    """
    if type(target) is not int or target<1 or len(rows)>target:
        raise ValueError("invalid primary capture selection target")
    if len({r["id"] for r in rows+deferred})!=len(rows)+len(deferred):
        raise ValueError("duplicate primary source capture identity")
    if any(r.get("source_status")!="CAPTURED" for r in rows+deferred):
        raise ValueError("uncaptured primary selection row")
    needed=target-len(rows)
    restored=deferred[:needed]
    for row in restored:
        row["source_selection"]="CAPTURED_CLIFF_FALLBACK_FOR_FIXED_TARGET"
    return rows+restored,deferred[needed:]


def source_capture(rpc, graph, directory, *, shard_index=0, shard_count=1, target=None):
    from arb.m5_four_to_six_source_capture import capture
    root=Path(directory)
    root.mkdir(parents=True,exist_ok=True)
    if graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY":
        raise ValueError("authenticated graph required")
    rows=[]
    blocked=[]
    deferred=[]
    venue_cache={}
    selected=[(i,r) for i,r in enumerate(graph["routes"]) if r.get("hops")==3]
    if (type(shard_index)is not int or type(shard_count)is not int
            or shard_count<1 or not 0<=shard_index<shard_count):
        raise ValueError("invalid three-hop route shard")
    if target is not None and (type(target)is not int or not 1<=target<=len(selected)):
        raise ValueError("invalid bounded source capture target")
    by_start,starts=capture_priority_indices(graph["routes"])
    from arb.m5_historical_capture_priority import is_historical_priority
    historical_priority_matches=sum(
        bool(by_start[mint]) and
        is_historical_priority(graph["routes"][by_start[mint][0]])
        for mint in starts)
    captured_starts=set()
    attempted=set()
    # For unsharded CI, try unserved mint starts first. Legacy shard paths
    # retain their original route modulo assignment.
    while True:
        if shard_count==1 and target is not None and len(rows)>=target:
            break
        if shard_count==1 and target is not None:
            index=capture_attempt_order(graph["routes"],by_start,starts,
                                        captured_starts,attempted)
            if index is None:
                break
            route=graph["routes"][index]
            j=next(j for j,(i,_) in enumerate(selected) if i==index)
        else:
            next_row=next(((j,i,r) for j,(i,r) in enumerate(selected)
                          if j%shard_count==shard_index and i not in attempted),None)
            if next_row is None:
                break
            j,index,route=next_row
        attempted.add(index)
        entry={"id":"3H-%02d"%(j+1),"graph_route_index":index,
               "mints":[route["start_mint"]]+[x["output"] for x in route["legs"]],
               "venues":[x["venue"] for x in route["legs"]],
               "pools":[x["pool"] for x in route["legs"]],
               "discovery_status":"AUTHENTICATED_CLOSED_CYCLE",
               "source_status":"NOT_CAPTURED",
               "atomic_build_status":"NOT_ATTEMPTED",
               "simulation_status":"NOT_ATTEMPTED",**SAFE}
        fixture=root/("source-%02d.json"%j)
        try:
            capture(rpc,graph,index,fixture,venue_cache=venue_cache)
            entry["source_status"]="CAPTURED"
            entry["fixture"]=fixture.name
            import hashlib
            entry["source_fixture_sha256"]=hashlib.sha256(fixture.read_bytes()).hexdigest()
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            entry["source_status"]="CAPTURE_BLOCKED"
            entry["diagnostic"]=str(exc)[:1000]
        if entry["source_status"]=="CAPTURED":
            hints=[];errors=[]
            if shard_count==1 and target is not None:
                try:
                    hints,errors=source_cliff_hints(json.loads(fixture.read_text()))
                except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
                    errors=[{"error_class":type(exc).__name__}]
            entry["source_cliff_hints"]=hints
            entry["source_cliff_hint_errors"]=errors
            if hints and route["start_mint"] in captured_starts:
                entry["source_selection"]="CAPTURED_REDUNDANT_START_CLIFF_DEFERRED"
                deferred.append(entry)
            else:
                entry["source_selection"]="CAPTURED_PRIMARY_CANDIDATE"
                rows.append(entry)
                captured_starts.add(route["start_mint"])
        else:
            blocked.append(entry)
        (root/"three-hop-inventory.json").write_text(json.dumps(
            {"status":"SOURCE_THREE_HOP_INVENTORY",
             "cycle_count":len(selected),"shard_index":shard_index,
             "shard_count":shard_count,"shard_cycle_count":len(rows),
             "attempted_source_captures":len(rows)+len(blocked)+len(deferred),
             "captured_but_not_selected_routes":deferred,
             "captured_but_not_selected_count":len(deferred),
             "source_cliff_selection_is_heuristic":True,
             "selected_graph_start_mints":len(starts),
             "source_captured_start_mints":len(captured_starts),
             "uncaptured_graph_start_mints":sorted(set(starts)-captured_starts),
             "source_capture_policy":"HISTORICAL_SIGNED_HINT_PER_MINT_THEN_DIRECTIONAL_NOVELTY_AND_REDUNDANT_CLIFF_DEFER",
             "historically_signed_route_hints_matched":historical_priority_matches,
             "historical_hint_not_current_verification":True,
             "blocked_source_routes":blocked,
             "cached_distinct_pool_directions":len(venue_cache),
            "three_hop_truncated":graph.get("cycle_coverage_by_hops",{}).get("3",{}).get("truncated"),
             "routes":rows,**SAFE},indent=2)+"\n")
    if shard_count==1 and target is not None:
        rows,deferred=capture_selection(rows,deferred,target=target)
        captured_starts={r["mints"][0] for r in rows}
        # Persist final selected and deferred inventories even if the target
        # could not be met. Keep each original graph route identity unchanged.
        (root/"three-hop-inventory.json").write_text(json.dumps(
            {"status":"SOURCE_THREE_HOP_INVENTORY",
             "cycle_count":len(selected),"shard_index":shard_index,
             "shard_count":shard_count,"shard_cycle_count":len(rows),
             "attempted_source_captures":len(rows)+len(blocked)+len(deferred),
             "captured_but_not_selected_routes":deferred,
             "captured_but_not_selected_count":len(deferred),
             "source_cliff_selection_is_heuristic":True,
             "selected_graph_start_mints":len(starts),
             "source_captured_start_mints":len(captured_starts),
             "uncaptured_graph_start_mints":sorted(set(starts)-captured_starts),
             "source_capture_policy":"HISTORICAL_SIGNED_HINT_PER_MINT_THEN_DIRECTIONAL_NOVELTY_AND_REDUNDANT_CLIFF_DEFER",
             "historically_signed_route_hints_matched":historical_priority_matches,
             "historical_hint_not_current_verification":True,
             "blocked_source_routes":blocked,
             "cached_distinct_pool_directions":len(venue_cache),
            "three_hop_truncated":graph.get("cycle_coverage_by_hops",{}).get("3",{}).get("truncated"),
             "routes":rows,**SAFE},indent=2)+"\n")
    if shard_count==1 and target is not None and len(rows)<target:
        raise RuntimeError(f"only {len(rows)}/{target} source-capturable routes; {len(blocked)} blocked")
    return rows

def source_capture_gap_summary(report):
    """Summarize uncaptured starting mints without treating hints as proof.

    A blocked route is not an authenticated simulation failure; do not
    ascribe a failed swap venue to a source-capture exception. This report
    records attempted source-capture alternatives, unique pool identities,
    and coarse diagnostic families only.
    """
    if (not isinstance(report,dict)
            or not isinstance(report.get("uncaptured_graph_start_mints"),list)
            or not isinstance(report.get("blocked_source_routes"),list)):
        raise ValueError("source capture report required")
    from collections import Counter,defaultdict
    missing=report["uncaptured_graph_start_mints"]
    if len(set(missing))!=len(missing) or any(
            not isinstance(m,str) or not m for m in missing):
        raise ValueError("malformed uncaptured mint identities")
    grouped=defaultdict(list)
    for row in report["blocked_source_routes"]:
        if not isinstance(row,dict):
            raise ValueError("malformed blocked source capture")
        mints=row.get("mints")
        if not isinstance(mints,list) or not mints or not isinstance(mints[0],str):
            raise ValueError("blocked source route missing start mint")
        grouped[mints[0]].append(row)
    details={}
    for mint in sorted(missing):
        rows=grouped.get(mint,[])
        if any(row.get("source_status")!="CAPTURE_BLOCKED" for row in rows):
            raise ValueError("untrusted source capture status")
        pools={(venue,pool) for row in rows
               for venue,pool in zip(row.get("venues",[]),row.get("pools",[]))
               if isinstance(venue,str) and isinstance(pool,str)}
        family_counts=Counter()
        for row in rows:
            diagnostic=row.get("diagnostic","")
            if not isinstance(diagnostic,str):
                raise ValueError("invalid capture diagnostic")
            # Group exception-family prefixes, not potentially sensitive RPC
            # responses, endpoint URLs, or misleading swap error inferences.
            prefix=diagnostic.split(":",1)[0].strip()
            family=prefix if prefix in (
                "ValueError","KeyError","TypeError","RuntimeError",
                "OSError","TimeoutError") else "UNCLASSIFIED"
            family_counts[family]+=1
        details[mint]={"source_capture_attempts":len(rows),
                       "distinct_attempted_pools":len(pools),
                       "diagnostic_families":dict(sorted(family_counts.items())),
                       "no_source_capture_attempt":not bool(rows)}
    return {"status":"SOURCE_CAPTURE_START_MINT_GAP_AUDIT",
        "uncaptured_start_mints":len(missing),
        "uncaptured_with_attempts":sum(
            bool(details[m]["source_capture_attempts"]) for m in missing),
        "uncaptured_without_attempts":sum(
            details[m]["no_source_capture_attempt"] for m in missing),
        "per_start_mint":details,
        "not_signed_simulation_evidence":True,**SAFE}


def orca_tick_array_input_retries(error, venues, amount):
    """Bounded smaller-input hypotheses for isolated Orca prefix error 6038.

    A range-exhaustion hypothesis is not proof of route success. Every retry
    still requires the same independently signed and rollback-verified receipt.
    """
    context=failed_instruction_context({"venues":venues,
                                        "pools":[""]*len(venues)},str(error))
    if (not isinstance(error,ValueError) or
            "signed prefix simulation failed" not in str(error) or
            context.get("failed_venue")!="orca" or
            context.get("program_error_code")!=6038):
        return []
    values=[amount//10,amount//100]
    return [a for i,a in enumerate(values) if a>0 and a<amount and
            a not in values[:i]]


def zero_output_input_retries(error, venues, amount):
    """Bounded higher-input hypotheses for signed prefix zero-output errors.

    Orca 6036 (AmountOutBelowMinimum) and Raydium CPMM 2505 (RequireGt)
    sometimes arise from amount quantization. Neither error establishes
    profitability, and only newly signed, rollback-verified receipts count.
    Keep trials bounded and avoid overflowing the signed u64 domain.
    """
    context=failed_instruction_context({"venues":venues,
                                        "pools":[""]*len(venues)},str(error))
    if not isinstance(error,ValueError) or "signed prefix simulation failed" not in str(error):
        return []
    venue,code=context.get("failed_venue"),context.get("program_error_code")
    if (venue,code) not in (("orca",6036),("raydium_cpmm",2505)):
        return []
    # Treat a CPMM 2505 as a potential amount-quantization issue only
    # when the program log explicitly reports a zero-side comparison.
    if venue=="raydium_cpmm" and not ("Left: 0" in str(error) and
                                    "Right: 0" in str(error)):
        return []
    return [amount*factor for factor in (10,100)
            if amount*factor<2**64]


def dlmm_bin_array_input_retries(error, venues, amount):
    """Test bounded smaller exact inputs only for proven DLMM bin-array 3005.

    Anchor 3005 is generic AccountNotEnoughKeys; never use it as a retry
    signal without both the signed-prefix failure and bin_array log identity.
    No missing bin array is created, and retries require full signed rollback
    evidence just like every original route.
    """
    context=failed_instruction_context(
        {"venues":venues,"pools":[""]*len(venues)},str(error))
    message=str(error)
    if (not isinstance(error,ValueError) or
            "signed prefix simulation failed" not in message or
            context.get("failed_venue")!="meteora_dlmm" or
            context.get("program_error_code")!=3005 or
            "account: bin_array" not in message or
            "AccountNotEnoughKeys" not in message):
        return []
    values=[amount//10,amount//100]
    return [a for i,a in enumerate(values) if a>0 and a<amount and
            a not in values[:i]]



def raydium_amm_v4_slippage_input_retries(error, venues, amount):
    """Bounded larger signed inputs for AMM v4's explicit error 30.

    This is a quantization/liquidity hypothesis, NOT an assertion that
    slippage is acceptable or that any route is executable. The signed
    builder retains a nonzero minimum output; every attempt requires its
    own signed-prefix simulation plus atomic/rollback verification.
    """
    message=str(error)
    context=failed_instruction_context(
        {"venues":venues,"pools":[""]*len(venues)},message)
    if (not isinstance(error,ValueError) or
            "signed prefix simulation failed" not in message or
            context.get("failed_venue")!="raydium_amm_v4" or
            context.get("program_error_code")!=30 or
            "AMM error: Exceeded desired slippage limit." not in message):
        return []
    return [amount*factor for factor in (10,100) if
            amount*factor<2**64]



def damm_v2_slippage_input_retries(error,venues,amount):
    """Try bounded independent sizes for the official DAMM v2 6002 error.

    The existing prefix and full atomic simulator retains nonzero output
    thresholds; a retry never changes slippage limits or proves liquidity.
    Larger amounts can resolve integer dust, while a smaller amount can
    fit bounded source liquidity. Neither hypothesis is acceptance.
    """
    message=str(error)
    context=failed_instruction_context({"venues":venues,"pools":[""]*len(venues)},message)
    if (not isinstance(error,ValueError)
            or type(amount) is not int or not 0<amount<2**64
            or "signed prefix simulation failed" not in message
            or context.get("failed_venue")!="meteora_damm_v2"
            or context.get("program_error_code")!=6002):
        return []
    return [candidate for candidate in (amount*10,amount//10)
            if 0<candidate<2**64 and candidate!=amount]


def offline_simulate(rpc,directory,*,amount=100000,shard_index=0,shard_count=1):
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.next_ten_signed_atomic_offline import run_four_to_six_venue
    import os
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1" or os.environ.get("SURFPOOL_DATASOURCE_RPC_URL"):
        raise ValueError("source-disconnected explicit offline Surfpool required")
    if type(amount)is not int or not 0<amount<2**64:
        raise ValueError("positive u64 exact input required")
    root=Path(directory)
    report=json.loads((root/"three-hop-inventory.json").read_text())
    if (type(shard_index)is not int or type(shard_count)is not int
            or shard_count<1 or not 0<=shard_index<shard_count):
        raise ValueError("invalid offline route shard")
    report["routes"]=[row for j,row in enumerate(report["routes"])
                      if j % shard_count == shard_index]
    report["shard_index"]=shard_index
    report["shard_count"]=shard_count
    report["shard_cycle_count"]=len(report["routes"])
    for row in report["routes"]:
        if row["source_status"]!="CAPTURED":
            continue
        row["atomic_build_status"]="BUILD_ATTEMPTED_NO_SIGNED_PACKET"
        row["simulation_status"]="NOT_ATTEMPTED"
        fixture=None
        try:
            fixture=json.loads((root/row["fixture"]).read_text())
            from arb.dlmm_offline_clock import align_permissioned_dlmm_clock
            row["offline_clock_alignment"]=align_permissioned_dlmm_clock(rpc,fixture)
            row["signed_exact_input_attempts"]=[]
            retry_amounts=[amount]
            receipt=None
            for amount_index,exact_input in enumerate(retry_amounts):
                try:
                    attempt={"amount_base_units":exact_input,"status":"RUNNING"}
                    row["signed_exact_input_attempts"].append(attempt)
                    receipt=run_four_to_six_venue(
                        rpc,fixture,amount_in=exact_input,
                        ephemeral_source_registry=True,retain_audit_evidence=True)
                    attempt["status"]="RECEIPT_RETURNED"
                    row["signed_exact_input_base_units"]=exact_input
                    break
                except ValueError as error:
                    attempt["status"]="PREFIX_OR_PREPARATION_REJECTED"
                    attempt["diagnostic"]=str(error)[:450]
                    if amount_index==0:
                        retry_amounts.extend(orca_tick_array_input_retries(
                            error,row["venues"],amount))
                        retry_amounts.extend(zero_output_input_retries(
                            error,row["venues"],amount))
                        retry_amounts.extend(dlmm_bin_array_input_retries(
                            error,row["venues"],amount))
                        retry_amounts.extend(raydium_amm_v4_slippage_input_retries(
                            error,row["venues"],amount))
                        retry_amounts.extend(damm_v2_slippage_input_retries(
                            error,row["venues"],amount))
                    if amount_index==len(retry_amounts)-1:
                        raise
            (root/("receipt-"+row["id"]+".json")).write_text(
                json.dumps(receipt,indent=2)+"\n")
            if receipt.get("signed_packet_crypto_bound") is True and receipt.get("signed_transaction_signature"):
                row["atomic_build_status"]="SIGNED_ATOMIC_PACKET_BUILT"
                row["signed_transaction_signature"]=receipt["signed_transaction_signature"]
                row["simulation_status"]=("SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED"
                    if receipt.get("signed_atomic_simulation_verified") is True
                    and receipt.get("rollback_failure_case_verified") is True
                    else "SIGNED_SIMULATION_NOT_VERIFIED")
                row["simulation_detail"]=receipt.get("status")
                row["positive_error"]=receipt.get("positive_error")
                if receipt.get("positive_error") is not None:
                    row["positive_program_log_tail"]=[str(x)[:180] for x in
                        (receipt.get("positive_logs") or [])[-8:]]
                row.update(failed_instruction_context(row,str(receipt.get("positive_error"))))
                if row["simulation_status"]=="SIGNED_SIMULATION_NOT_VERIFIED":
                    row["diagnostic"]=json.dumps({
                        "receipt_status":receipt.get("status"),
                        "positive_error":receipt.get("positive_error"),
                        "signed_atomic_simulation_verified":receipt.get("signed_atomic_simulation_verified"),
                        "rollback_failure_case_verified":receipt.get("rollback_failure_case_verified"),
                    },sort_keys=True)[:500]
                row["compute_units"]=receipt.get("positive_units_consumed")
            else:
                row["atomic_build_status"]="NO_VERIFIABLE_SIGNED_PACKET"
                row["simulation_status"]="NOT_ATTEMPTED"
                row["diagnostic"]=receipt.get("status")
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            row["diagnostic"]=type(exc).__name__+": "+str(exc)[:950]
            row.update(failed_instruction_context(row,str(exc)))
            if (row.get("failed_venue")=="orca" and
                    row.get("program_error_code")==6038 and
                    isinstance(fixture,dict)):
                # Explain a source-verified zero-liquidity cliff when present.
                # This is diagnostic only: preserve the signed failure.
                from arb.whirlpool_ticks import authenticated_downward_liquidity_cliff
                try:
                    row["orca_source_liquidity_cliff"]=authenticated_downward_liquidity_cliff(
                        fixture,row["failed_instruction_index"])
                except (ValueError,KeyError,TypeError,RuntimeError,OSError) as audit_error:
                    row["orca_source_liquidity_audit_error"]=(
                        type(audit_error).__name__+": "+str(audit_error)[:240])
            row["simulation_status"]="NOT_ATTEMPTED_OR_ABORTED_DURING_PREPARATION"
        report["status"]="OFFLINE_THREE_HOP_ATOMIC_BUILD_AND_SIMULATION_INVENTORY"
        report["build_confirmed"]=sum(r["atomic_build_status"]=="SIGNED_ATOMIC_PACKET_BUILT" for r in report["routes"])
        report["simulations_verified"]=sum(r["simulation_status"]=="SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED" for r in report["routes"])
        (root/"three-hop-inventory.json").write_text(json.dumps(report,indent=2)+"\n")
    return report

def audit_primary_shard(directory):
    """Re-decode retained primary packets using the shared independent audit.

    No signing, local RPC or quote SDK. Bind the exact original source
    fixture, positive and negative packets, CPI and SPL/rollback evidence.
    """
    import hashlib,re
    from arb.blockzilla_multihop import audit_signed_core,reserve_receipt_signatures
    root=Path(directory)
    report=json.loads((root/"three-hop-inventory.json").read_text())
    if (report.get("status")!="OFFLINE_THREE_HOP_ATOMIC_BUILD_AND_SIMULATION_INVENTORY"
            or any(report.get(k) is not False for k in SAFE)
            or not isinstance(report.get("routes"),list)):
        raise ValueError("invalid primary offline shard inventory")
    routes=report["routes"]
    if len(routes)!=14 or len({r["id"] for r in routes})!=len(routes):
        raise ValueError("invalid primary shard route coverage")
    seen=set();accepted=[]
    for row in routes:
        if row.get("simulation_status")!="SIGNED_SIMULATION_AND_ROLLBACK_VERIFIED":
            continue
        rid=row["id"];name=row["fixture"]
        if (not re.fullmatch(r"3H-[0-9]{2,4}",rid)
                or not re.fullmatch(r"source-[0-9]{2,4}\.json",name)
                or row.get("source_status")!="CAPTURED"
                or row.get("atomic_build_status")!="SIGNED_ATOMIC_PACKET_BUILT"
                or any(row.get(k) is not False for k in SAFE)):
            raise ValueError("invalid accepted primary receipt identity")
        fixture_raw=(root/name).read_bytes()
        fixture_hash=hashlib.sha256(fixture_raw).hexdigest()
        if row.get("source_fixture_sha256")!=fixture_hash:
            raise ValueError("primary source fixture differs from source-phase digest")
        receipt_raw=(root/("receipt-"+rid+".json")).read_bytes()
        fixture=json.loads(fixture_raw);receipt=json.loads(receipt_raw)
        mints=row["mints"];venues=row["venues"];pools=row["pools"]
        if len(mints)!=4 or len(venues)!=3 or len(pools)!=3 or mints[0]!=mints[-1]:
            raise ValueError("invalid primary route topology")
        amount=row["signed_exact_input_base_units"]
        if row.get("signed_transaction_signature")!=receipt.get("signed_transaction_signature"):
            raise ValueError("primary signature inventory differs from retained receipt")
        source_row={"hops":3,"source_slot":fixture["state_accounts_observed_slot"],
            "legs":[{"venue":v,"pool":p,"input":mints[i],"output":mints[i+1]}
                    for i,(v,p) in enumerate(zip(venues,pools))]}
        audit=audit_signed_core(receipt,fixture,source_row,amount)
        reserve_receipt_signatures(receipt,seen)
        accepted.append({"id":rid,"start_mint":mints[0],"pools":pools,
            "source_slot":source_row["source_slot"],"amount":amount,
            "fixture_sha256":fixture_hash,
            "receipt_sha256":hashlib.sha256(receipt_raw).hexdigest(),"audit":audit})
    if len(accepted)!=report["simulations_verified"] or len(seen)!=2*len(accepted):
        raise ValueError("primary independent acceptance count mismatch")
    return {"status":"PRIMARY_SHARD_RECORDED_PACKETS_INDEPENDENTLY_RECHECKED",
        "shard":report["shard_index"],"audited":len(accepted),
        "verified_route_ids":[r["id"] for r in accepted],
        "distinct_packet_signatures":sorted(seen),"attempts":accepted,
        "rpc_response_cryptographically_attested":False,**SAFE}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--phase",choices=("source","offline"),required=True)
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--graph")
    p.add_argument("--directory",required=True)
    p.add_argument("--amount",type=int,default=100000)
    p.add_argument("--source-target",type=int,default=None)
    p.add_argument("--shard-index",type=int,default=0)
    p.add_argument("--shard-count",type=int,default=1)
    args=p.parse_args()
    if args.phase=="source":
        if not args.graph: p.error("--graph required for source")
        result=source_capture(args.rpc,json.loads(Path(args.graph).read_text()),args.directory,
                              shard_index=args.shard_index,shard_count=args.shard_count,target=args.source_target)
        print(json.dumps({"three_hop_capture_attempts":len(result),
                          "source_captured":sum(r["source_status"]=="CAPTURED" for r in result)}))
    else:
        r=offline_simulate(args.rpc,args.directory,amount=args.amount,
                           shard_index=args.shard_index,shard_count=args.shard_count)
        print(json.dumps({"cycle_count":r["cycle_count"],
                          "signed_builds":r.get("build_confirmed",0),
                          "verified_simulations":r.get("simulations_verified",0)}))

if __name__=="__main__":
    main()
