"""Bounded archive-derived 4–6 hop research using existing SOL engines.

The committed registry is only a source of identity hints. The existing
capture engine reauthenticates every leg before exporting a single-slot
fixture. No pool is admitted or counted toward the primary inventory.
"""
import argparse
import base64
from collections import defaultdict, deque
import json
import os
from pathlib import Path

from arb.blockzilla_discovery import SAFE, VENUES, digest, registry_ids, write
from arb.blockzilla_ci_gate import check_evidence
from arb.opportunity_graph import cycles, MAX_POOLS
from arb.pumpswap_local_simulation import local_rpc_only
from arb.source_snapshot_manifest import verify
from arb.m5_signed_start_mint_economics import WSOL

from arb.blockzilla_size_plan import CONTROL_AMOUNTS as AMOUNTS, evaluate as size_plan, verify_plan

MAX_CAPTURE_PER_HOPS=4
MAX_FOUR_FIVE_CAPTURED=2
MAX_SIX_HOP_CAPTURE_ATTEMPTS=8
ORIGINAL_DIVERSITY_ATTEMPTS=4
MAX_SIX_HOP_CAPTURED=2
MAX_PUMP_CAPTURED=2
MAX_PUMP_CAPTURE_ATTEMPTS=4
MAX_ROUTES=2*MAX_FOUR_FIVE_CAPTURED+MAX_SIX_HOP_CAPTURED+MAX_PUMP_CAPTURED
# Coarse venue-account pressure estimates used ONLY to prioritize six-hop
# hints; actual signed message keys and SVM acceptance remain authoritative.
VENUE_LOCK_PRESSURE={"raydium_cpmm":8,"orca":9,"meteora_damm_v2":10,
    "raydium_clmm":11,"meteora_dlmm":12,"raydium_amm_v4":14,"pumpswap":18}
MAX_GRAPH_CYCLES=600
MAX_EDGE_VISITS=250000


def seed_window(rows, seed, *, hops, maximum=MAX_POOLS):
    """Necessary reachability filter for a simple cycle through one edge.

    Removing the seed leaves a return path between its endpoints. For an
    edge (u,v) on that path, dist(a,u)+1+dist(v,b) <= hops-1 (or reverse).
    Shortest-distance filtering is necessary, not sufficient: the existing
    cycle engine still checks distinct pools, closed paths and exact length.
    Unlike an immediate-neighbor window, this retains the middle of a
    six-edge ring. The capped window may still omit eligible cycles.
    """
    if type(hops) is not int or not 4<=hops<=6 or type(maximum) is not int or not 1<=maximum<=MAX_POOLS:
        raise ValueError("invalid seed window budget")
    identity=(seed["venue"],seed["address"])
    a,b=seed["mints"]
    adjacency=defaultdict(set)
    others=[]
    for pool in rows:
        if pool["venue"] not in VENUES or (pool["venue"],pool["address"])==identity:
            continue
        u,v=pool["mints"]
        adjacency[u].add(v);adjacency[v].add(u)
        others.append(pool)
    def distances(start):
        result={start:0}
        pending=deque([start])
        while pending:
            u=pending.popleft()
            if result[u]>=hops-1:
                continue
            for v in sorted(adjacency[u]):
                if v not in result:
                    result[v]=result[u]+1
                    pending.append(v)
        return result
    da,db=distances(a),distances(b)
    eligible=[]
    for pool in others:
        u,v=pool["mints"]
        distance=min(da.get(u,hops)+db.get(v,hops),
                     da.get(v,hops)+db.get(u,hops))
        if distance<=hops-2:
            # Heuristic only. Keep short return paths first, then lighter
            # venues in the six-hop case; retain a stable identity order.
            rank=(distance,VENUE_LOCK_PRESSURE[pool["venue"]] if hops==6 else 0,
                  pool["venue"],pool["address"])
            eligible.append((rank,pool))
    eligible.sort(key=lambda item:item[0])
    window=[seed]+[p for _,p in eligible[:maximum-1]]
    return window,{"eligible_pool_hints":1+len(eligible),"pool_hints":len(window),
                   "pool_window_truncated":len(eligible)+1>maximum,
                   "shortest_return_edges":da.get(b)}


def candidate_routes(baseline,new_pools):
    new=registry_ids(new_pools)
    if new & registry_ids(baseline) or any(p.get("source_verified_only") is not True for p in new_pools):
        raise ValueError("novel source-verified identities required")
    all_rows=baseline+new_pools
    # Per-seed bounded neighborhood, prioritize edges incident on novel mints.
    # The existing graph enumerator is used in explicit hint-only mode.
    found={}
    windows=[]
    for seed in new_pools:
        anchors=set(seed["mints"])
        stats={"seed":[seed["venue"],seed["address"]],"windows_by_hops":{},
               "cycle_counts_by_hops":{},"cycle_limit_reached_by_hops":{}}
        windows.append(stats)
        for hops in (4,5,6):
            # Search an independent no-Orca window as well as the normal
            # window. A result cap in the normal window must not starve
            # alternatives that do not depend on missing Whirlpool arrays.
            variants=[("ALL_VENUES",all_rows)]
            if hops==6:
                if seed["venue"]!="orca":
                    variants.append(("NO_ORCA",[p for p in all_rows if p["venue"]!="orca"]))
                # Independent bounded traversal prevents lexicographic
                # cycle caps from exhausting the low-pressure candidates.
                # Keep the seed even if its own venue is expensive.
                light={"raydium_cpmm","orca","meteora_damm_v2"}|{seed["venue"]}
                variants.append(("LIGHT_VENUE_PRIORITY",[p for p in all_rows if p["venue"] in light]))
                variants.append(("ALL_VENUE_PRIORITY",all_rows))
            stats["windows_by_hops"][str(hops)]={}
            stats["cycle_counts_by_hops"][str(hops)]=0
            stats["cycle_limit_reached_by_hops"][str(hops)]=False
            for label,variant in variants:
                window,window_stats=seed_window(variant,seed,hops=hops)
                search={}
                paths=cycles(window,anchors=anchors,max_hops=hops,min_hops=hops,
                             max_cycles=MAX_GRAPH_CYCLES,truncate=True,hint_only=True,
                             required_first_pool=(seed["venue"],seed["address"]),
                             max_edge_visits=MAX_EDGE_VISITS,search_stats=search,
                             venue_priority=VENUE_LOCK_PRESSURE if label.endswith("PRIORITY") else None)
                stats["windows_by_hops"][str(hops)][label]={**window_stats,**search}
                stats["cycle_counts_by_hops"][str(hops)]+=len(paths)
                stats["cycle_limit_reached_by_hops"][str(hops)] |= search["stop_reason"]=="CYCLE_LIMIT"
                for row in paths:
                    identities={(l["venue"],l["pool"]) for l in row["legs"]}
                    if not identities & new or len({l["pool"] for l in row["legs"]})!=hops:
                        continue
                    if len(row["venues"])<2:
                        continue
                    legs=row["legs"]
                    # Rotate to WSOL where possible for direct fee denomination.
                    if any(l["input"]==WSOL for l in legs):
                        idx=next(i for i,l in enumerate(legs) if l["input"]==WSOL)
                        legs=legs[idx:]+legs[:idx]
                    key=tuple((l["venue"],l["pool"],l["input"]) for l in legs)
                    found[key]={**row,"legs":legs,"start_mint":legs[0]["input"],
                                "novel_pool_identities":[list(k) for k in sorted(identities & new)],
                                "topology_only":True,**SAFE}
    by_hops={}
    for hops in (4,5,6):
        rows=[r for r in found.values() if r["hops"]==hops]
        for row in rows:
            row["heuristic_venue_lock_pressure"]=sum(VENUE_LOCK_PRESSURE[l["venue"]] for l in row["legs"])
        rows.sort(key=lambda r:(-len(r["novel_pool_identities"]),r["start_mint"]!=WSOL,
                  r["heuristic_venue_lock_pressure"] if hops==6 else 0,
                  -len(r["venues"]),tuple((l["venue"],l["pool"]) for l in r["legs"])))
        # Prefer an independent pool set for the second capture attempt,
        # rather than a rotation of an already failing fixture.
        by_hops[hops]=diverse_candidates(rows,new,hops=hops)
    return by_hops,windows


def diverse_candidates(rows,new,*,hops):
    """Select distinct sets and minimize repeated non-seed dependencies.

    Keep the first ranked choice; the second six-hop choice prefers an
    Orca-free route if available. Later choices minimize repeated Whirlpool
    dependencies, then repeated other pool identities. This is not a claim
    of liquidity or source availability.
    """
    remaining=[]
    seen_sets=set()
    for row in rows:
        ids=frozenset((l["venue"],l["pool"]) for l in row["legs"])
        if ids not in seen_sets:
            seen_sets.add(ids)
            remaining.append((len(remaining),row,ids))
    chosen=[]
    used=defaultdict(int)
    maximum=MAX_SIX_HOP_CAPTURE_ATTEMPTS if hops==6 else MAX_CAPTURE_PER_HOPS
    while remaining and len(chosen)<maximum:
        def score(item):
            rank,row,ids=item
            repeated=ids-new
            orca=sum(used[k] for k in repeated if k[0]=="orca")
            overlap=sum(used[k] for k in repeated)
            no_orca_penalty=int("orca" in row["venues"]) if hops==6 and len(chosen)==1 else 0
            if not chosen:
                return (rank,)
            if hops==6:
                if len(chosen)<ORIGINAL_DIVERSITY_ATTEMPTS:
                    return (no_orca_penalty,orca,overlap,rank)
                pressure=sum(VENUE_LOCK_PRESSURE[l["venue"]] for l in row["legs"])
                return (pressure,overlap,orca,rank)
            # A second 4/5-hop fixture should explore other dependencies,
            # rather than merely repeating the original seed's bridge.
            return (overlap,rank)
        selected=min(remaining,key=score)
        remaining.remove(selected)
        _,row,ids=selected
        chosen.append(row)
        for k in ids-new:
            used[k]+=1
    return chosen


def pump_triangles(baseline,new_pools):
    """Dedicated source-hint triangles with one PumpSwap edge and one novel edge.

    Enumerate WSOL-rooted triangles by mint-pair index, not by filtering the
    truncated four-to-six-hop search. Reserve both orientations of the same
    topology for independent buy/sell-direction evidence. No source, quote,
    or signed success is inferred by the graph.
    """
    new=registry_ids(new_pools)
    if new & registry_ids(baseline) or any(p.get("source_verified_only") is not True for p in new_pools):
        raise ValueError("novel source-verified identities required")
    pairs=defaultdict(list)
    by_id={}
    for p in baseline+new_pools:
        key=(p["venue"],p["address"])
        if p["venue"] not in VENUES or key in by_id or len(p["mints"])!=2 or p["mints"][0]==p["mints"][1]:
            continue
        by_id[key]=p
        pairs[frozenset(p["mints"])].append(p)
    # Build triangles from a novel edge incident on a PumpSwap pair. This
    # includes a novel PumpSwap seed itself and novel non-PumpSwap bridges.
    triangles={}
    for pump in by_id.values():
        if pump["venue"]!="pumpswap" or WSOL not in pump["mints"]:
            continue
        token=next(x for x in pump["mints"] if x!=WSOL)
        for seed in new_pools:
            if seed["venue"]=="pumpswap" and seed["address"]!=pump["address"]:
                continue
            if (seed["venue"],seed["address"])==(pump["venue"],pump["address"]):
                others=[p for p in by_id.values() if p["venue"]!="pumpswap" and token in p["mints"]]
            else:
                others=[seed]
            for edge in others:
                if edge["venue"]=="pumpswap" or token not in edge["mints"] and WSOL not in edge["mints"]:
                    continue
                for middle in edge["mints"]:
                    if middle in (token,WSOL):
                        continue
                    # edge joins token or WSOL to middle. The other leg
                    # must join middle to the remaining endpoint.
                    edge_at=token if token in edge["mints"] else WSOL
                    other_at=WSOL if edge_at==token else token
                    for bridge in pairs.get(frozenset((middle,other_at)),[]):
                        if bridge["venue"]=="pumpswap":
                            continue
                        first,last=(edge,bridge) if edge_at==token else (bridge,edge)
                        rows=(pump,first,last)
                        ids=frozenset((p["venue"],p["address"]) for p in rows)
                        if len(ids)!=3 or len({p["address"] for p in rows})!=3 or not ids & new:
                            continue
                        if len({p["venue"] for p in rows})<2:
                            continue
                        triangles[tuple(sorted(ids))]=(rows,token,middle,ids)
    ranked=sorted(triangles.values(),key=lambda x:(-len(x[3]&new),
        sum(VENUE_LOCK_PRESSURE[p["venue"]] for p in x[0]),
        -len({p["venue"] for p in x[0]}),tuple(sorted(x[3]))))
    routes=[]
    # Two topologies maximum, with opposite signed input directions for each.
    for rows,token,middle,ids in ranked[:MAX_PUMP_CAPTURE_ATTEMPTS//2]:
        forward=[(rows[0],WSOL,token),(rows[1],token,middle),(rows[2],middle,WSOL)]
        reverse=[(p,out,inp) for p,inp,out in reversed(forward)]
        for direction,ordered in (("FROM_WSOL",forward),("TO_WSOL",reverse)):
            legs=[{"venue":p["venue"],"pool":p["address"],"input":inp,"output":out}
                  for p,inp,out in ordered]
            routes.append({"status":"HINT_ONLY_UNQUOTED","hops":3,"start_mint":WSOL,
                "legs":legs,"venues":sorted({l["venue"] for l in legs}),
                "novel_pool_identities":[list(k) for k in sorted(ids&new)],
                "heuristic_venue_lock_pressure":sum(VENUE_LOCK_PRESSURE[p["venue"]] for p in rows),
                "pump_direction":direction,"topology_only":True,
                "simulation_verified":False,"net_profit_verified":False,**SAFE})
    return routes


def fixture_identity(fixture,row):
    verify(fixture)
    legs=row["legs"]
    if (fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE"
            or fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL"
            or any(fixture.get(k) is not False for k in SAFE)
            or fixture["route_venues"]!=[l["venue"] for l in legs]
            or fixture["route_pool_addresses"]!=[l["pool"] for l in legs]
            or fixture["route_mints"]!=[legs[0]["input"]]+[l["output"] for l in legs]):
        raise ValueError("multihop fixture identity mismatch")


def prepare(rpc, evidence_dir, directory, baseline, route):
    from arb.m5_four_to_six_source_capture import capture
    from arb.next_ten_fork_pool_probe import source_clock
    from arb.m5_source_indicative_route_chain import research_chain
    local_rpc_only(rpc)
    root=Path(directory);root.mkdir(parents=True,exist_ok=True)
    check_evidence(evidence_dir,baseline,route)
    raw=(Path(evidence_dir)/"source-authentication.json").read_bytes()
    source=json.loads(raw)
    choices,windows=candidate_routes(baseline,source["new_source_verified_pools"])
    # Keep established 4–6-hop research budget separate from targeted PumpSwap.
    choices[3]=pump_triangles(baseline,source["new_source_verified_pools"])
    report={"status":"BLOCKZILLA_MULTIHOP_SOURCE_RESEARCH","source_report_sha256":digest(raw),
            "excluded_from_primary_inventory":True,"windows":windows,
            "bounded_candidates_by_hops":{str(k):len(v) for k,v in choices.items()},
            "routes":[],"source_captured":0,"capture_caps_by_hops":{"3":MAX_PUMP_CAPTURED,
                "4":MAX_FOUR_FIVE_CAPTURED,"5":MAX_FOUR_FIVE_CAPTURED,"6":MAX_SIX_HOP_CAPTURED},**SAFE}
    from arb.blockzilla_source_footprint import source_footprint,select_six_hop_sources
    six_candidates=[]
    venue_cache={}
    for hops, rows in choices.items():
        captured_for_hops=0
        cap=MAX_SIX_HOP_CAPTURED if hops==6 else MAX_PUMP_CAPTURED if hops==3 else MAX_FOUR_FIVE_CAPTURED
        captured_directions=set()
        for index,row in enumerate(rows):
            if hops==3 and row["pump_direction"] in captured_directions:
                continue
            item={**row,"id":f"BZ{hops}-{index+1:02d}","capture_status":"NOT_CAPTURED"}
            report["routes"].append(item)
            try:
                path=root/(item["id"]+"-fixture.json")
                capture(rpc,{"status":"BLOCKZILLA_HINT_GRAPH_ONLY","routes":[row],**SAFE},
                        0,path,allow_hint_graph=True,venue_cache=venue_cache)
                fixture=json.loads(path.read_text())
                fixture_identity(fixture,item)
                clock=source_clock(rpc);item["source_clock"]=clock
                item.update(capture_status="CAPTURED",fixture_sha256=digest(path.read_bytes()),
                            source_slot=fixture["state_accounts_observed_slot"])
                report["source_captured"]+=1
                captured_for_hops+=1
                if hops==6:
                    item["source_account_footprint"]=source_footprint(fixture)
                    six_candidates.append(item)
                if hops==3:
                    captured_directions.add(row["pump_direction"])
                quotes=[]
                for amount in AMOUNTS:
                    result=research_chain(fixture,amount_in=amount,
                        observed_unix=clock["unix_timestamp"],allow_modeled_dlmm=True,
                        allow_modeled_pumpswap=True)
                    quotes.append({"amount":amount,"quote":result})
                quote_path=root/(item["id"]+"-quotes.json")
                write(quote_path,quotes)
                item["quote_sha256"]=digest(quote_path.read_bytes())
                if hops!=6 and captured_for_hops>=cap:
                    break
                if hops==6 and sum((c["source_account_footprint"].get("within_preferred_key_budget") is True)
                        for c in six_candidates)>=cap:
                    break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
                item.update(error_class=type(exc).__name__,diagnostic=str(exc)[:300])
                if hops==6 and item["capture_status"]=="CAPTURED" and item not in six_candidates:
                    # The fixture cannot enter the selected inventory until
                    # its source-bound footprint can be reproduced.
                    item["capture_status"]="FOOTPRINT_PREFLIGHT_BLOCKED"
                    report["source_captured"]-=1
                    captured_for_hops-=1
                if hops!=6 and captured_for_hops>=cap:
                    break
            finally:
                write(root/"multihop-source.json",report)
    chosen=select_six_hop_sources(six_candidates,cap=MAX_SIX_HOP_CAPTURED)
    report["six_hop_footprint_selected_ids"]=chosen
    report["source_captured_before_footprint_selection"]=report["source_captured"]
    for item in six_candidates:
        if item["id"] not in chosen:
            item["capture_status"]="CAPTURED_NOT_SELECTED_FOOTPRINT"
            report["source_captured"]-=1
    report["source_footprint_deferred_count"]=len(six_candidates)-len(chosen)
    report["source_cached_distinct_pool_directions"]=len(venue_cache)
    report["six_hop_preferred_footprint_count"]=sum(
        c["source_account_footprint"].get("within_preferred_key_budget") is True for c in six_candidates)
    write(root/"multihop-source.json",report)
    return report


def offline(rpc,directory):
    from arb.next_ten_signed_atomic_offline import run_four_to_six_venue
    from arb.dlmm_offline_clock import align_permissioned_dlmm_clock
    from arb.m5_signed_start_mint_economics import signed_net_economics
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1" or os.environ.get("SURFPOOL_DATASOURCE_RPC_URL"):
        raise ValueError("explicit disconnected fork required")
    root=Path(directory)
    raw=(root/"multihop-source.json").read_bytes()
    source=json.loads(raw)
    selected=[r for r in source["routes"] if r["capture_status"]=="CAPTURED"]
    if (len(selected)>MAX_ROUTES or any(source.get(k) is not False for k in SAFE)
            or source.get("excluded_from_primary_inventory") is not True):
        raise ValueError("invalid source research report")
    report={"status":"BLOCKZILLA_MULTIHOP_SIGNED_RESEARCH","source_report_sha256":digest(raw),
            "excluded_from_primary_inventory":True,"attempts":[],"accepted":0,**SAFE}
    programs={}
    report["size_plans"]={}
    fixtures={}
    from arb.blockzilla_size_plan import rank_comparable_grid
    lock=Path("tools/meteora_damm_v2_reference/Cargo.lock")
    report["official_damm_sdk_lock_sha256"]=digest(lock.read_bytes())
    for row in selected:
        path=root/(row["id"]+"-fixture.json")
        fixture_raw=path.read_bytes()
        if digest(fixture_raw)!=row["fixture_sha256"]:
            raise ValueError("multihop source fixture digest mismatch")
        fixture=json.loads(fixture_raw);fixture_identity(fixture,row)
        plan=size_plan(fixture,observed_unix=row["source_clock"]["unix_timestamp"])
        report["size_plans"][row["id"]]=plan
        fixtures[row["id"]]=fixture
    # Compute all fixture size plans and comparable rankings before signing
    # any route. Ranking does not suppress the original controls.
    report["pre_sign_grid_rankings"]=rank_comparable_grid(report["size_plans"])
    write(root/"multihop-signed.json",report)
    for row in selected:
        fixture=fixtures[row["id"]]
        plan=report["size_plans"][row["id"]]
        for amount in plan["signed_amounts"]:
            item={"id":row["id"],"amount":amount,"status":"BLOCKED"}
            report["attempts"].append(item)
            try:
                item["clock_alignment"]=align_permissioned_dlmm_clock(rpc,fixture)
                receipt=run_four_to_six_venue(rpc,fixture,amount_in=amount,
                    program_cache=programs,ephemeral_source_registry=True,retain_audit_evidence=True)
                if any(receipt.get(k) is not False for k in SAFE):
                    raise ValueError("unsafe signed research receipt")
                if receipt.get("signed_atomic_simulation_verified") is True:
                    receipt["signed_start_mint_economics"]=signed_net_economics(receipt,
                        start_mint=fixture["route_mints"][0],source_slot=row["source_slot"],
                        fixture=fixture,observed_unix=row["source_clock"]["unix_timestamp"])
                name=f'{row["id"]}-{amount}-receipt.json'
                write(root/name,receipt)
                item.update(status=receipt["status"],receipt=name,receipt_sha256=digest((root/name).read_bytes()),
                            resolved_account_key_count=receipt.get("resolved_account_key_count"),
                            runtime_account_lock_rejected=receipt.get("runtime_account_lock_rejected") is True)
                if receipt.get("signed_atomic_simulation_verified") is True:
                    report["accepted"]+=1
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
                item.update(error_class=type(exc).__name__,diagnostic=str(exc)[:300])
            finally:
                write(root/"multihop-signed.json",report)
    write(root/"multihop-signed.json",report)
    return report


def decode_packet(wire,claimed_hash,claimed_signature,lookup_evidence):
    from solders.transaction import VersionedTransaction
    from solders.message import MessageV0
    from solders.pubkey import Pubkey
    from solders.address_lookup_table_account import AddressLookupTableAccount
    from arb.atomic_v0_lookup import ALT_PROGRAM,resolved_v0_keys
    raw=base64.b64decode(wire,validate=True)
    if not 1<=len(raw)<=1232 or digest(raw)!=claimed_hash:
        raise ValueError("signed packet digest or size mismatch")
    tx=VersionedTransaction.from_bytes(raw)
    tx.verify_and_hash_message()
    if bytes(tx)!=raw or str(tx.signatures[0])!=claimed_signature:
        raise ValueError("signed packet signature mismatch")
    lookup=None
    if isinstance(tx.message,MessageV0):
        info=lookup_evidence["account"]
        if info["owner"]!=ALT_PROGRAM or info["executable"] is not False or info["data"][1]!="base64":
            raise ValueError("untrusted isolated ALT readback")
        table=base64.b64decode(info["data"][0],validate=True)
        if (len(table)<88 or (len(table)-56)%32 or len(table)>56+240*32
                or table[:12]!=b"\x01\x00\x00\x00"+(2**64-1).to_bytes(8,"little")):
            raise ValueError("invalid isolated ALT bytes")
        lookup=AddressLookupTableAccount(Pubkey.from_string(lookup_evidence["address"]),
                    [Pubkey.from_bytes(table[i:i+32]) for i in range(56,len(table),32)])
        keys=resolved_v0_keys(tx.message,lookup)
    else:
        if lookup_evidence is not None:
            raise ValueError("legacy message has unexpected lookup evidence")
        keys=list(tx.message.account_keys)
    return tx,lookup,keys


def audit_account_lock_rejection(receipt,fixture,row,amount):
    """Authenticate rejected packet and independently resolve its account set.

    A runtime lock rejection is not a rollback control or successful swap.
    RPC response remains recorded evidence, not a cryptographic attestation.
    """
    fixture_identity(fixture,row)
    n=row["hops"]
    if (receipt.get("status")!="SIGNED_ACCOUNT_LOCK_LIMIT_REJECTED"
            or receipt.get("runtime_account_lock_rejected") is not True
            or receipt.get("positive_error")!="TooManyAccountLocks"
            or receipt.get("state_account_manifest_sha256")!=fixture["state_account_manifest_sha256"]
            or receipt.get("state_accounts_observed_slot")!=row["source_slot"]
            or receipt.get("route_pool_addresses")!=fixture["route_pool_addresses"]
            or receipt.get("route_mints")!=fixture["route_mints"]
            or receipt.get("route_venues")!=fixture["route_venues"]
            or any(receipt.get(k) is not False for k in (*SAFE,"signed_atomic_simulation_verified",
                    "signed_cpi_per_leg_verified","rollback_failure_case_verified"))):
        raise ValueError("rejected packet source or status mismatch")
    evidence=receipt["recorded_rejected_packet_evidence"]
    response=receipt["recorded_rejected_positive_response"]
    if (response.get("err")!="TooManyAccountLocks" or response.get("innerInstructions")
            or response.get("logs") or response.get("unitsConsumed")!=0):
        raise ValueError("recorded account lock rejection response inconsistent")
    tx,lookup,keys=decode_packet(receipt["signed_transaction_wire_base64"],
        receipt["signed_transaction_sha256"],receipt["signed_transaction_signature"],
        evidence["isolated_lookup_account"])
    user_accounts=evidence["ephemeral_token_accounts"]
    if (len(keys)!=len(set(keys)) or len(keys)!=receipt["resolved_account_key_count"]
            or len(tx.message.account_keys)!=receipt["static_account_key_count"]
            or len(keys)-len(tx.message.account_keys)!=receipt["lookup_account_key_count"]
            or len(tx.message.instructions)!=n or len(user_accounts)!=n+1
            or len(set(user_accounts))!=n+1 or str(keys[0])!=evidence["ephemeral_authority"]
            or evidence["persistent_before"]!=[amount]+[0]*n
            or evidence["persistent_after_rejected"]!=evidence["persistent_before"]
            or receipt["planned_inputs"][0]!=amount):
        raise ValueError("rejected packet key count, input or persistent readback mismatch")
    for i,ix in enumerate(tx.message.instructions):
        metas=[str(keys[k]) for k in ix.accounts]
        if (str(keys[ix.program_id_index])!=VENUES[fixture["route_venues"][i]][0]
                or fixture["route_pool_addresses"][i] not in metas
                or not set(user_accounts[i:i+2])<=set(metas)):
            raise ValueError("rejected packet route account mismatch")
    return {"status":"REJECTED_PACKET_SIGNATURE_AND_RESOLVED_KEYS_RECHECKED",
        "resolved_account_key_count":len(keys),"static_account_key_count":len(tx.message.account_keys),
        "lookup_account_key_count":len(keys)-len(tx.message.account_keys),
        "runtime_error":response["err"],"persistent_user_balances_unchanged":True,
        "signed_atomic_simulation_verified":False,"rollback_failure_case_verified":False,
        "rpc_response_cryptographically_attested":False,**SAFE}


def audit_receipt(receipt,fixture,row,amount):
    from arb.atomic_graph_coordinator import audit_n_leg_cpi,audit_n_leg_balances,signed_n_leg_post_balances
    from arb.next_ten_signed_atomic_offline import top_level_events
    from arb.m5_source_indicative_route_chain import research_chain
    from arb.m5_signed_start_mint_economics import signed_net_economics
    fixture_identity(fixture,row)
    n=row["hops"];mints=fixture["route_mints"];venues=fixture["route_venues"]
    if (receipt.get("status")!="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"
            or any(receipt.get(k) is not False for k in SAFE)
            or receipt["state_account_manifest_sha256"]!=fixture["state_account_manifest_sha256"]
            or receipt["state_accounts_observed_slot"]!=row["source_slot"]
            or receipt["route_mints"]!=mints or receipt["route_venues"]!=venues
            or receipt["route_pool_addresses"]!=fixture["route_pool_addresses"]):
        raise ValueError("unaccepted or mismatched source receipt")
    evidence=receipt["recorded_n_leg_audit_evidence"]
    positive,lookup,keys=decode_packet(receipt["signed_transaction_wire_base64"],
        receipt["signed_transaction_sha256"],receipt["signed_transaction_signature"],evidence["isolated_lookup_account"])
    negative,_,bad_keys=decode_packet(receipt["negative_signed_transaction_wire_base64"],
        receipt["negative_signed_transaction_sha256"],receipt["negative_signed_transaction_signature"],evidence["isolated_lookup_account"])
    accounts=evidence["ephemeral_token_accounts"];owner=evidence["ephemeral_authority"]
    if receipt.get("resolved_account_key_count")!=len(keys):
        raise ValueError("compiled resolved key count differs from recorded receipt")
    if (len(accounts)!=n+1 or len(set(accounts))!=n+1 or str(keys[0])!=owner
            or keys!=bad_keys or positive.message.recent_blockhash!=negative.message.recent_blockhash
            or positive.signatures[0]==negative.signatures[0]
            or len(positive.message.instructions)!=n or len(negative.message.instructions)!=n):
        raise ValueError("negative message context differs")
    programs=[VENUES[v][0] for v in venues]
    for i,(a,b) in enumerate(zip(positive.message.instructions,negative.message.instructions)):
        metas=[str(keys[k]) for k in a.accounts]
        if (str(keys[a.program_id_index])!=programs[i] or a.program_id_index!=b.program_id_index
                or a.accounts!=b.accounts or fixture["route_pool_addresses"][i] not in metas
                or not set(accounts[i:i+2])<=set(metas)
                or (i<n-1 and a.data!=b.data) or (i==n-1 and a.data==b.data)):
            raise ValueError("compiled route or negative instruction mismatch")
    pr,nr=evidence["positive_response"],evidence["negative_response"]
    expected=[event for p in programs for event in ([p,"invoke"],[p,"success"])]
    if pr.get("err") is not None or top_level_events(pr.get("logs"),set(programs))!=expected:
        raise ValueError("positive program trace mismatch")
    expected[-1][1]="failed"
    if (not isinstance(nr.get("err"),dict) or nr["err"].get("InstructionError",[None])[0]!=n-1
            or top_level_events(nr.get("logs"),set(programs))!=expected):
        raise ValueError("negative final-leg failure mismatch")
    amounts=receipt["planned_inputs"]
    if len(amounts)!=n or amounts[0]!=amount or evidence["persistent_before"]!=[amount]+[0]*n:
        raise ValueError("initial signed exact-input mismatch")
    post=signed_n_leg_post_balances(pr,accounts,mints,owner)
    if post!=receipt["positive_post_balances_base_units"]:
        raise ValueError("recorded post balances differ")
    cpi=audit_n_leg_cpi(positive,pr,accounts,amounts,lookup=lookup)
    balances=audit_n_leg_balances(amounts,evidence["persistent_before"],post,
        rollback_balances=evidence["persistent_after_negative"],later_instruction_failed=True)
    if balances["status"]!="N_LEG_BALANCES_AND_ROLLBACK_RECONCILED":
        raise ValueError("recorded rollback reconciliation failed")
    model=research_chain(fixture,amount_in=amount,observed_unix=row["source_clock"]["unix_timestamp"],
                         allow_modeled_dlmm=True,allow_modeled_pumpswap=True)
    from arb.meteora_dlmm_signed_event_audit import stable_execution_timestamp,audit_swap_event
    execution_unix=stable_execution_timestamp(evidence)
    execution_model=(research_chain(fixture,amount_in=amount,observed_unix=execution_unix,
        allow_modeled_dlmm=True,allow_modeled_pumpswap=True) if execution_unix is not None else None)
    # Diagnose each venue independently using actual signed inputs. A single
    # blocked or mismatched upstream model must not hide downstream evidence.
    from arb.fixture_all_venue_signed_quotes import quote_leg
    actual_outputs=amounts[1:]+[post[-1]]
    leg_samples=[]
    for i,(actual_in,actual_out) in enumerate(zip(amounts,actual_outputs)):
        q=quote_leg(fixture,leg_index=i,amount_in=actual_in,
                    observed_unix=row["source_clock"]["unix_timestamp"])
        if (q.get("pool")!=fixture["route_pool_addresses"][i] or q.get("venue")!=venues[i]
                or q.get("source_slot")!=row["source_slot"] or any(q.get(k) is not False for k in SAFE)):
            raise ValueError("multihop native model source identity mismatch")
        prediction=q.get("predicted_output_base_units")
        if venues[i]=="meteora_dlmm" and type(prediction) is not int:
            env=q.get("native_fee_envelope") or {}
            prediction=(env.get("source_derived_dynamic_fee_quote") or {}).get("amount_out")
        # Independently reprice each actual signed input at the stable clock,
        # including downstream legs of an incomplete or divergent source chain.
        eq=None
        execution_prediction=None
        if execution_unix is not None:
            eq=quote_leg(fixture,leg_index=i,amount_in=actual_in,observed_unix=execution_unix)
            if (eq.get("pool")!=q["pool"] or eq.get("venue")!=venues[i]
                    or eq.get("source_slot")!=row["source_slot"] or any(eq.get(k) is not False for k in SAFE)):
                raise ValueError("execution-clock native model identity mismatch")
            execution_prediction=eq.get("predicted_output_base_units")
            if venues[i]=="meteora_dlmm" and type(execution_prediction) is not int:
                execution_prediction=((eq.get("native_fee_envelope") or {}).get(
                    "source_derived_dynamic_fee_quote") or {}).get("amount_out")
            if venues[i]=="pumpswap" and type(execution_prediction) is not int:
                from arb.pumpswap_source_fee_envelope import selected_directional_model
                chosen=selected_directional_model(eq.get("native_fee_envelope"))
                if chosen is not None:
                    execution_prediction=chosen["amount_out"]
        dlmm_comparison=None
        if venues[i]=="meteora_dlmm":
            dlmm_comparison=audit_swap_event(pr,keys,positive.message.instructions[i],q["pool"],owner,i,actual_in,actual_out)
            if execution_unix is not None:
                effective=(eq.get("native_fee_envelope") or {}).get("source_derived_dynamic_fee_quote") or {}
                ep=effective.get("amount_out")
                dlmm_comparison["execution_clock_modeled_output"]=ep
                dlmm_comparison["execution_clock_delta"]=ep-actual_out if type(ep) is int else None
                dlmm_comparison["execution_clock_fee_input_units"]=effective.get("fee_input_base_units")
                dlmm_comparison["execution_clock_fee_output_units"]=effective.get("fee_output_base_units")
        orca_comparison=None
        if venues[i]=="orca" and execution_unix is not None:
            ep=execution_prediction
            orca_comparison={"observed_unix":execution_unix,"modeled_output":ep,
                "delta":ep-actual_out if type(ep) is int else None,
                "exact_sample_match":ep==actual_out if type(ep) is int else None,
                "protocol_exact_verified":False,**SAFE}
        pump_comparison=None
        if venues[i]=="pumpswap":
            from arb.pumpswap_source_fee_envelope import compare_directional_scenarios
            pump_comparison=compare_directional_scenarios(q.get("native_fee_envelope"),actual_out)
            from arb.pumpswap_signed_event_audit import audit_event
            pump_comparison["event_and_cpi"]=audit_event(fixture,positive,pr,keys,accounts,i,actual_in,actual_out)
            from arb.pumpswap_source_fee_envelope import selected_directional_model
            chosen=selected_directional_model(q.get("native_fee_envelope"))
            pump_comparison["preselected_source_model"]=chosen
            pump_comparison["preselected_model_matches"]=chosen is not None and chosen["amount_out"]==actual_out
        leg_samples.append({"venue":venues[i],"pool":q["pool"],"leg_index":i,
            "input":actual_in,"signed_output":actual_out,"modeled_output":prediction,
            "delta":prediction-actual_out if type(prediction) is int else None,
            "quote_status":q.get("quote_status"),"reason":q.get("reason"),
            "pumpswap_scenario_comparison":pump_comparison,
            "orca_execution_clock_comparison":orca_comparison,
            "execution_clock_leg_comparison":None if eq is None else {
                "modeled_output":execution_prediction,
                "delta":execution_prediction-actual_out if type(execution_prediction) is int else None,
                "preselected_research_model":venues[i]=="pumpswap",**SAFE},
            "dlmm_execution_clock_comparison":dlmm_comparison,
            "protocol_exact_verified":False,**SAFE})
    economics=signed_net_economics(receipt,start_mint=mints[0],source_slot=row["source_slot"],
                                  fixture=fixture,observed_unix=row["source_clock"]["unix_timestamp"])
    if economics!=receipt["signed_start_mint_economics"]:
        raise ValueError("signed economics recomputation differs")
    from arb.signed_cpi_native_funding import audit_funding
    funding=audit_funding(pr,keys,owner,economics)
    return {"status":"N_LEG_PACKET_AND_RECORDED_RESPONSE_RECHECKED","cpi":cpi,
            "balances":balances,"source_model":model,"signed_economics":economics,
            "observed_system_funding":funding,"execution_clock_unix":execution_unix,
            "execution_clock_before":evidence.get("positive_execution_clock_before"),
            "execution_clock_after":evidence.get("positive_execution_clock_after"),
            "execution_clock_model":execution_model,
            "execution_clock_model_matches_terminal":execution_model is not None and execution_model.get("output_base_units")==post[-1],
            "resolved_account_key_count":len(keys),"native_leg_samples":leg_samples,
            "model_matches_terminal":model.get("output_base_units")==post[-1],
            "rpc_response_cryptographically_attested":False,"net_profit_verified":False,**SAFE}


def audit(source_dir,signed_dir):
    root=Path(signed_dir);src=Path(source_dir)
    source_raw=(src/"multihop-source.json").read_bytes()
    source=json.loads(source_raw);signed=json.loads((root/"multihop-signed.json").read_text())
    if (source.get("status")!="BLOCKZILLA_MULTIHOP_SOURCE_RESEARCH"
            or signed.get("status")!="BLOCKZILLA_MULTIHOP_SIGNED_RESEARCH"
            or any(r.get(k) is not False for r in (source,signed) for k in SAFE)
            or source.get("excluded_from_primary_inventory") is not True
            or signed.get("excluded_from_primary_inventory") is not True):
        raise ValueError("unsafe multihop source/signed report")
    if signed["source_report_sha256"]!=digest(source_raw):
        raise ValueError("signed source report binding mismatch")
    rows={r["id"]:r for r in source["routes"]}
    if len(rows)!=len(source["routes"]) or any(not isinstance(rid,str) or not __import__("re").fullmatch(r"BZ[3-6]-[0-9]{2}",rid) for rid in rows):
        raise ValueError("duplicate or invalid captured route identity")
    captured={r["id"]:r for r in rows.values() if r["capture_status"]=="CAPTURED"}
    from arb.blockzilla_source_footprint import source_footprint,select_six_hop_sources
    six_candidates=[]
    for row in rows.values():
        if row["hops"]!=6 or row["capture_status"] not in ("CAPTURED","CAPTURED_NOT_SELECTED_FOOTPRINT"):
            continue
        raw=(src/(row["id"]+"-fixture.json")).read_bytes()
        if digest(raw)!=row["fixture_sha256"]:
            raise ValueError("six-hop footprint source digest mismatch")
        fixture=json.loads(raw);fixture_identity(fixture,row)
        if source_footprint(fixture)!=row["source_account_footprint"]:
            raise ValueError("independent unsigned source footprint differs")
        six_candidates.append(row)
    chosen=select_six_hop_sources(six_candidates,cap=MAX_SIX_HOP_CAPTURED)
    if (chosen!=source.get("six_hop_footprint_selected_ids")
            or set(chosen)!={rid for rid,row in captured.items() if row["hops"]==6}
            or source.get("source_captured")!=len(captured)
            or source.get("source_footprint_deferred_count")!=len(six_candidates)-len(chosen)):
        raise ValueError("source footprint selection coverage mismatch")
    lock=Path("tools/meteora_damm_v2_reference/Cargo.lock")
    if signed.get("official_damm_sdk_lock_sha256")!=digest(lock.read_bytes()):
        raise ValueError("offline and independent SDK dependency locks differ")
    if set(signed.get("size_plans",{}))!=set(captured):
        raise ValueError("missing or extra pre-sign size plan")
    plans={}
    for rid,row in captured.items():
        raw=(src/(rid+"-fixture.json")).read_bytes()
        if digest(raw)!=row["fixture_sha256"]:
            raise ValueError("size plan source fixture digest mismatch")
        fixture=json.loads(raw);fixture_identity(fixture,row)
        plans[rid]=verify_plan(signed["size_plans"][rid],fixture,observed_unix=row["source_clock"]["unix_timestamp"])
    from arb.blockzilla_size_plan import rank_comparable_grid
    rankings=rank_comparable_grid(plans)
    if rankings!=signed.get("pre_sign_grid_rankings"):
        raise ValueError("pre-sign comparable ranking differs from independent recomputation")
    expected={(rid,amount) for rid,plan in plans.items() for amount in plan["signed_amounts"]}
    attempts=[(a["id"],a["amount"]) for a in signed["attempts"]]
    if len(attempts)!=len(set(attempts)) or set(attempts)!=expected:
        raise ValueError("missing or duplicate signed size attempt")
    accepted=sum(a["status"]=="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED" for a in signed["attempts"])
    if accepted!=signed["accepted"]:
        raise ValueError("signed acceptance count does not reconcile")
    report={"status":"BLOCKZILLA_MULTIHOP_INDEPENDENT_RECHECK" if accepted else
            "NO_ACCEPTED_MULTIHOP_RECEIPTS_TO_AUDIT","audited":0,
            "source_captured":source["source_captured"],"signed_attempt_count":len(attempts),
            "net_profit_verified":False,
            "runner_accepted":signed["accepted"],"attempts":[],**SAFE}
    report["rejected_attempts"]=[]
    report["six_hop_footprints_recomputed"]=len(six_candidates)
    report["six_hop_footprint_selected_ids"]=chosen
    report["six_hop_footprint_candidates"]=[{"id":r["id"],"selected":r["id"] in chosen,
        "footprint":r["source_account_footprint"]} for r in six_candidates]
    for attempt in signed["attempts"]:
        if attempt["status"]!="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED":
            rejected={"id":attempt["id"],"amount":attempt["amount"],"status":attempt["status"],
                      "diagnostic":attempt.get("diagnostic"),"runtime_account_lock_rejected":False,
                      "recorded_rejection_digest_checked":False,**SAFE}
            if attempt.get("receipt") is not None:
                expected_name=f'{attempt["id"]}-{attempt["amount"]}-receipt.json'
                if attempt["receipt"]!=expected_name:
                    raise ValueError("rejected receipt filename does not match attempt")
                raw=(root/expected_name).read_bytes()
                if digest(raw)!=attempt.get("receipt_sha256"):
                    raise ValueError("rejected receipt digest mismatch")
                result=json.loads(raw)
                if (result.get("status")!=attempt["status"] or
                        any(result.get(k) is not False for k in SAFE) or
                        result.get("signed_atomic_simulation_verified") is not False):
                    raise ValueError("inconsistent rejected signed receipt")
                rejected["recorded_rejection_digest_checked"]=True
                rejected["runtime_account_lock_rejected"]=result.get("runtime_account_lock_rejected") is True
                rejected["positive_error"]=result.get("positive_error")
                if rejected["runtime_account_lock_rejected"]:
                    original=rows[attempt["id"]]
                    original_raw=(src/(original["id"]+"-fixture.json")).read_bytes()
                    if digest(original_raw)!=original["fixture_sha256"]:
                        raise ValueError("rejected packet source fixture digest mismatch")
                    rejected["packet_audit"]=audit_account_lock_rejection(result,json.loads(original_raw),original,attempt["amount"])
            report["rejected_attempts"].append(rejected)
            continue
        item={"id":attempt["id"],"amount":attempt["amount"]}
        report["attempts"].append(item)
        try:
            row=rows[attempt["id"]]
            fixture_raw=(src/(row["id"]+"-fixture.json")).read_bytes()
            expected_name=f'{attempt["id"]}-{attempt["amount"]}-receipt.json'
            if attempt["receipt"]!=expected_name:
                raise ValueError("accepted receipt filename does not match attempt")
            receipt_raw=(root/expected_name).read_bytes()
            if digest(fixture_raw)!=row["fixture_sha256"] or digest(receipt_raw)!=attempt["receipt_sha256"]:
                raise ValueError("source or receipt digest mismatch")
            item["audit"]=audit_receipt(json.loads(receipt_raw),json.loads(fixture_raw),row,attempt["amount"])
            estimate=(row.get("source_account_footprint") or {}).get("resolved_account_key_estimate")
            if type(estimate) is int:
                actual=item["audit"]["resolved_account_key_count"]
                item["audit"]["unsigned_footprint_comparison"]={"estimated_keys":estimate,
                    "signed_resolved_keys":actual,"delta":estimate-actual,**SAFE}
            report["audited"]+=1
        except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
            item.update(error_class=type(exc).__name__,diagnostic=str(exc)[:300])
    report["size_plan_recomputed_count"]=len(plans)
    report["size_plans"]=plans
    report["pre_sign_grid_rankings"]=rankings
    report["pre_sign_ranking_recomputed"]=True
    report["modeled_grid_sample_count"]=sum(len(p["samples"]) for p in plans.values())
    report["positive_modeled_net_grid_samples"]=sum(p["positive_estimated_net_count"] for p in plans.values())
    report["native_pricing_summary"]=pricing_summary(report["attempts"])
    report["execution_clock_pricing_summary"]=execution_pricing_summary(report["attempts"])
    report["estimated_economics_by_input"]=rank_estimated_economics(report["attempts"])
    write(root/"multihop-audit.json",report)
    return report


def pricing_summary(attempts):
    counts={}
    for row in attempts:
        for sample in row.get("audit",{}).get("native_leg_samples",[]):
            venue=sample["venue"]
            c=counts.setdefault(venue,{"samples":0,"predicted":0,"exact_matches":0,
                "blocked":0,"fee_scenario_comparisons":0,"fee_scenario_match_samples":0})
            c["samples"]+=1
            if type(sample.get("modeled_output")) is int:
                c["predicted"]+=1
                c["exact_matches"]+=int(sample["delta"]==0)
            else:
                c["blocked"]+=1
            comparison=sample.get("pumpswap_scenario_comparison")
            if isinstance(comparison,dict) and comparison.get("scenario_count",0)>0:
                c["fee_scenario_comparisons"]+=1
                c["fee_scenario_match_samples"]+=int(comparison["matching_scenario_count"]>0)
    return counts


def execution_pricing_summary(attempts):
    counts={}
    for row in attempts:
        for sample in row.get("audit",{}).get("native_leg_samples",[]):
            c=counts.setdefault(sample["venue"],{"samples":0,"predicted":0,"matches":0,"blocked":0})
            c["samples"]+=1
            comparison=sample.get("execution_clock_leg_comparison") or {}
            if type(comparison.get("modeled_output")) is int:
                c["predicted"]+=1
                c["matches"]+=int(comparison["delta"]==0)
            else:
                c["blocked"]+=1
    return counts


def rank_estimated_economics(attempts):
    """Rank only independently audited outcomes with comparable denomination/size.

    This is a retrospective local simulation ranking, not a quote-based
    trading recommendation or evidence of paid fees, executable profits,
    priority fee coverage, or a new opportunity.
    """
    groups=defaultdict(list)
    for row in attempts:
        evidence=row.get("audit",{})
        econ=evidence.get("signed_economics",{})
        if (evidence.get("status")!="N_LEG_PACKET_AND_RECORDED_RESPONSE_RECHECKED"
                or any(econ.get(k) is not False for k in SAFE)
                or type(econ.get("estimated_net_delta_start_mint_base_units")) is not int
                or type(econ.get("observed_local_fork_gross_delta_start_mint_base_units")) is not int):
            continue
        key=(econ["start_mint"],row["amount"])
        groups[key].append({"id":row["id"],"gross_delta":econ["observed_local_fork_gross_delta_start_mint_base_units"],
            "estimated_cost":econ["estimated_cost_start_mint_base_units"],
            "estimated_net_delta":econ["estimated_net_delta_start_mint_base_units"],
            "model_matches_terminal":evidence["model_matches_terminal"],
            "observed_creation_funding_lamports":evidence.get("observed_system_funding",{}).get("observed_creation_funding_lamports"),
            "estimated_net_after_observed_funding":evidence.get("observed_system_funding",{}).get("estimated_net_after_observed_funding_wsol_units"),
            "net_profit_verified":False,**SAFE})
    return [{"start_mint":mint,"input_base_units":amount,
        "status":"SIGNED_LOCAL_ESTIMATED_NET_RANKING_ONLY",
        "routes":sorted(rows,key=lambda x:(-x["estimated_net_delta"],x["id"])),**SAFE}
        for (mint,amount),rows in sorted(groups.items())]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--phase",choices=("source","offline","audit"),required=True)
    p.add_argument("--directory",required=True)
    p.add_argument("--source-directory")
    p.add_argument("--evidence-directory")
    p.add_argument("--route",choices=("true","false"))
    args=p.parse_args()
    if args.phase=="source":
        result=prepare("http://127.0.0.1:8899",args.evidence_directory,args.directory,
                       json.loads(Path("arb/pool_registry.json").read_text())["pools"],args.route)
    elif args.phase=="offline":
        result=offline("http://127.0.0.1:8899",args.directory)
    else:
        result=audit(args.source_directory,args.directory)
    print(json.dumps(result,sort_keys=True))
    return 2 if args.phase=="audit" and result["audited"]!=result["runner_accepted"] else 0


if __name__=="__main__":
    raise SystemExit(main())
