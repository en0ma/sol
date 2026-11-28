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

AMOUNTS=(100000, 1000000)
MAX_CAPTURE_PER_HOPS=2
MAX_SIX_HOP_CAPTURE_ATTEMPTS=4
MAX_SIX_HOP_CAPTURED=2
MAX_PUMP_CAPTURED=2
MAX_PUMP_CAPTURE_ATTEMPTS=4
MAX_ROUTES=4+MAX_PUMP_CAPTURED
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
            if hops==6 and seed["venue"]!="orca":
                variants.append(("NO_ORCA",[p for p in all_rows if p["venue"]!="orca"]))
            stats["windows_by_hops"][str(hops)]={}
            stats["cycle_counts_by_hops"][str(hops)]=0
            stats["cycle_limit_reached_by_hops"][str(hops)]=False
            for label,variant in variants:
                window,window_stats=seed_window(variant,seed,hops=hops)
                search={}
                paths=cycles(window,anchors=anchors,max_hops=hops,min_hops=hops,
                             max_cycles=MAX_GRAPH_CYCLES,truncate=True,hint_only=True,
                             required_first_pool=(seed["venue"],seed["address"]),
                             max_edge_visits=MAX_EDGE_VISITS,search_stats=search)
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
            remaining.append((row,ids))
    chosen=[]
    used=defaultdict(int)
    maximum=MAX_SIX_HOP_CAPTURE_ATTEMPTS if hops==6 else MAX_CAPTURE_PER_HOPS
    while remaining and len(chosen)<maximum:
        def score(item):
            row,ids=item
            repeated=ids-new
            orca=sum(used[k] for k in repeated if k[0]=="orca")
            overlap=sum(used[k] for k in repeated)
            no_orca_penalty=int("orca" in row["venues"]) if hops==6 and len(chosen)==1 else 0
            return (no_orca_penalty,orca,overlap,remaining.index(item)) if hops==6 and chosen else (remaining.index(item),)
        selected=min(remaining,key=score)
        remaining.remove(selected)
        row,ids=selected
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
            "routes":[],"source_captured":0,**SAFE}
    for hops, rows in choices.items():
        captured_for_hops=0
        cap=MAX_SIX_HOP_CAPTURED if hops==6 else MAX_PUMP_CAPTURED if hops==3 else 1
        captured_directions=set()
        for index,row in enumerate(rows):
            if hops==3 and row["pump_direction"] in captured_directions:
                continue
            item={**row,"id":f"BZ{hops}-{index+1:02d}","capture_status":"NOT_CAPTURED"}
            report["routes"].append(item)
            try:
                path=root/(item["id"]+"-fixture.json")
                capture(rpc,{"status":"BLOCKZILLA_HINT_GRAPH_ONLY","routes":[row],**SAFE},
                        0,path,allow_hint_graph=True)
                fixture=json.loads(path.read_text())
                fixture_identity(fixture,item)
                item.update(capture_status="CAPTURED",fixture_sha256=digest(path.read_bytes()),
                            source_slot=fixture["state_accounts_observed_slot"])
                report["source_captured"]+=1
                captured_for_hops+=1
                if hops==3:
                    captured_directions.add(row["pump_direction"])
                clock=source_clock(rpc);item["source_clock"]=clock
                quotes=[]
                for amount in AMOUNTS:
                    result=research_chain(fixture,amount_in=amount,
                        observed_unix=clock["unix_timestamp"],allow_modeled_dlmm=True)
                    quotes.append({"amount":amount,"quote":result})
                quote_path=root/(item["id"]+"-quotes.json")
                write(quote_path,quotes)
                item["quote_sha256"]=digest(quote_path.read_bytes())
                if captured_for_hops>=cap:
                    break
            except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
                item.update(error_class=type(exc).__name__,diagnostic=str(exc)[:300])
                if captured_for_hops>=cap:
                    break
            finally:
                write(root/"multihop-source.json",report)
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
    for row in selected:
        path=root/(row["id"]+"-fixture.json")
        fixture_raw=path.read_bytes()
        if digest(fixture_raw)!=row["fixture_sha256"]:
            raise ValueError("multihop source fixture digest mismatch")
        fixture=json.loads(fixture_raw);fixture_identity(fixture,row)
        for amount in AMOUNTS:
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
                         allow_modeled_dlmm=True)
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
        pump_comparison=None
        if venues[i]=="pumpswap":
            from arb.pumpswap_source_fee_envelope import compare_directional_scenarios
            pump_comparison=compare_directional_scenarios(q.get("native_fee_envelope"),actual_out)
            from arb.pumpswap_signed_event_audit import audit_event
            pump_comparison["event_and_cpi"]=audit_event(fixture,positive,pr,keys,accounts,i,actual_in,actual_out)
        leg_samples.append({"venue":venues[i],"pool":q["pool"],"leg_index":i,
            "input":actual_in,"signed_output":actual_out,"modeled_output":prediction,
            "delta":prediction-actual_out if type(prediction) is int else None,
            "quote_status":q.get("quote_status"),"reason":q.get("reason"),
            "pumpswap_scenario_comparison":pump_comparison,
            "protocol_exact_verified":False,**SAFE})
    economics=signed_net_economics(receipt,start_mint=mints[0],source_slot=row["source_slot"],
                                  fixture=fixture,observed_unix=row["source_clock"]["unix_timestamp"])
    if economics!=receipt["signed_start_mint_economics"]:
        raise ValueError("signed economics recomputation differs")
    return {"status":"N_LEG_PACKET_AND_RECORDED_RESPONSE_RECHECKED","cpi":cpi,
            "balances":balances,"source_model":model,"signed_economics":economics,
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
    expected={(r["id"],amount) for r in rows.values() if r["capture_status"]=="CAPTURED" for amount in AMOUNTS}
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
    for attempt in signed["attempts"]:
        if attempt["status"]!="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED":
            continue
        item={"id":attempt["id"],"amount":attempt["amount"]}
        report["attempts"].append(item)
        try:
            row=rows[attempt["id"]]
            fixture_raw=(src/(row["id"]+"-fixture.json")).read_bytes()
            receipt_raw=(root/attempt["receipt"]).read_bytes()
            if digest(fixture_raw)!=row["fixture_sha256"] or digest(receipt_raw)!=attempt["receipt_sha256"]:
                raise ValueError("source or receipt digest mismatch")
            item["audit"]=audit_receipt(json.loads(receipt_raw),json.loads(fixture_raw),row,attempt["amount"])
            report["audited"]+=1
        except (ValueError,RuntimeError,KeyError,TypeError,OSError) as exc:
            item.update(error_class=type(exc).__name__,diagnostic=str(exc)[:300])
    report["native_pricing_summary"]=pricing_summary(report["attempts"])
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
