"""Read-only authenticated pool-pair discovery for the next ten atomic routes.

Run against upstream-backed *local* Surfpool before shutting it down.
No account mutation, signer generation, or broadcast; readiness != execution.
"""
import argparse
import base64
import json
from pathlib import Path
from arb.next_ten_atomic_routes import BATCH_10,route_batch
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.orca_whirlpool import PROGRAM as ORCA, decode as orca_decode
from arb.raydium_cpmm import PROGRAM as CPMM, decode as cpmm_decode, verify_vaults
from arb.meteora_damm_v2 import PROGRAM as DAMM, decode as damm_decode, verify as damm_verify
from arb.meteora_dlmm import PROGRAM as DLMM, decode as dlmm_decode, verify as dlmm_verify
from arb.pumpswap_pool import PROGRAM as PUMP, decode as pump_decode, verify as pump_verify
from arb.raydium_clmm import PROGRAM as CLMM, decode as clmm_decode, verify as clmm_verify
from arb.raydium_amm_v4 import decode as amm4_decode
from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED

PROGRAMS={"orca":ORCA,"raydium_cpmm":CPMM,"meteora_damm_v2":DAMM,
          "meteora_dlmm":DLMM,"pumpswap":PUMP,
          "raydium_clmm":CLMM,
          "raydium_amm_v4":next(k for k,v in RECOGNIZED_UNSUPPORTED.items() if v=="raydium_amm_v4")}
DECODERS={"orca":orca_decode,"raydium_cpmm":cpmm_decode,
          "meteora_damm_v2":damm_decode,"meteora_dlmm":dlmm_decode,
          "pumpswap":pump_decode,"raydium_clmm":clmm_decode,
          "raydium_amm_v4":amm4_decode}
MINT_KEYS={"orca":("token_mint_a","token_mint_b"),
           "raydium_cpmm":("token_0_mint","token_1_mint"),
           "meteora_damm_v2":("token_a_mint","token_b_mint"),
           "meteora_dlmm":("token_x_mint","token_y_mint"),
           "pumpswap":("base_mint","quote_mint"),
           "raydium_clmm":("token_mint_0","token_mint_1"),
           "raydium_amm_v4":("base_mint","quote_mint")}
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}

CLOCK_SYSVAR="SysvarC1ock11111111111111111111111111111111"

def source_clock(rpc):
    """Read source-fork Clock sysvar; never use wall clock as protocol evidence."""
    info=call(rpc,"getAccountInfo",[CLOCK_SYSVAR,
        {"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not isinstance(info,dict) or info.get("owner")!="Sysvar1111111111111111111111111111111111111":
        raise ValueError("source Clock sysvar absent or owner mismatch")
    raw=base64.b64decode(info["data"][0],validate=True)
    if len(raw)!=40:
        raise ValueError("source Clock sysvar length mismatch")
    slot=int.from_bytes(raw[0:8],"little")
    unix_timestamp=int.from_bytes(raw[32:40],"little",signed=True)
    if unix_timestamp<0:
        raise ValueError("negative source Clock timestamp")
    return {"slot":slot,"unix_timestamp":unix_timestamp}

def snapshot(rpc, pool, venue):
    local_rpc_only(rpc)
    if venue not in PROGRAMS:
        raise ValueError("unsupported venue")
    result=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])
    info=result.get("value") if isinstance(result,dict) else None
    if not isinstance(info,dict) or info.get("owner")!=PROGRAMS[venue] or info.get("executable") is not False:
        raise ValueError("missing or wrongly owned "+venue+" pool")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("invalid pool encoding")
    state=DECODERS[venue](base64.b64decode(data[0],validate=True))
    if venue=="raydium_cpmm":
        evidence=verify_vaults(rpc,pool,state,expected_mints=None)
    elif venue=="meteora_damm_v2":
        evidence=damm_verify(rpc,pool,state)
    elif venue=="meteora_dlmm":
        evidence=dlmm_verify(rpc,pool,state)
    elif venue=="pumpswap":
        evidence=pump_verify(rpc,pool,state)
    elif venue=="raydium_clmm":
        evidence=clmm_verify(rpc,pool,state)
    elif venue=="raydium_amm_v4":
        from arb.raydium_amm_v4_preflight import verify_pool_market
        evidence=verify_pool_market(rpc,pool,state)
    else:
        # Orca vaults must be authenticated, not just decode a state hint.
        from arb.token_vaults import TOKEN_PROGRAM, decode_token_account
        addresses=[state["token_vault_a"],state["token_vault_b"]]
        response=call(rpc,"getMultipleAccounts",[
            addresses,{"encoding":"base64","commitment":"confirmed"}])
        vaults=response.get("value") if isinstance(response,dict) else None
        if not isinstance(vaults,list) or len(vaults)!=2:
            raise ValueError("Orca vault snapshot missing")
        for i,vault in enumerate(vaults):
            if not isinstance(vault,dict) or vault.get("owner")!=TOKEN_PROGRAM:
                raise ValueError("Orca vault owner unsupported")
            token=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
            mint=state["token_mint_a" if i==0 else "token_mint_b"]
            if token["mint"]!=mint or token["amount_base_units"]<=0:
                raise ValueError("Orca vault mint or balance mismatch")
        evidence={"slot":response.get("context",{}).get("slot")}
    slot=evidence.get("slot")
    if type(slot) is not int or slot<0:
        raise ValueError("authenticated venue slot missing")
    a,b=(state[key] for key in MINT_KEYS[venue])
    if a==b:
        raise ValueError("duplicate pool mint")
    result={"venue":venue,"pool":pool,"mints":[a,b],
            "slot":slot,"authenticated":True,**SAFETY}
    if venue=="meteora_dlmm":
        # Status==enabled does not imply that a permissioned pool is live.
        result["source_swap_activation"]={
            name:state[name] for name in
            ("status","pair_type","activation_type","activation_point",
             "pre_activation_duration","pre_activation_swap_address")}
    return result

def candidates(registry):
    entries=registry.get("pools")
    if not isinstance(entries,list):
        raise ValueError("missing pool registry")
    result={v:[] for v in PROGRAMS}
    for entry in entries:
        if not isinstance(entry,dict):
            continue
        v=entry.get("venue")
        a=entry.get("address")
        if v in result and isinstance(a,str) and a and a not in result[v]:
            result[v].append(a)
    # Always check the two real working signed pool fixtures.
    from arb.damm_cpmm_atomic_offline import DAMM_POOL, CPMM_POOL
    for venue,pool in (("meteora_damm_v2",DAMM_POOL),("raydium_cpmm",CPMM_POOL)):
        if pool not in result[venue]:
            result[venue].insert(0,pool)
    return result

def prioritized_probe_addresses(registry, addresses, batch, *, maximum=12):
    """Prioritize *hinted* cross-venue pair overlap before source RPC reads.

    This is scheduling ONLY. Mint labels in registry cannot authenticate any
    pool, and snapshot() still independently checks the actual program owner,
    decoder, mint identity and reserves before route consideration.
    """
    if type(maximum) is not int or not 1<=maximum<=24:
        raise ValueError("bounded paired source pool probes required")
    entries=registry.get("pools") if isinstance(registry,dict) else None
    if not isinstance(entries,list) or not isinstance(addresses,dict):
        raise ValueError("malformed pool probe inventory")
    relevant={venue for route in batch for venue in route}
    peers={venue:set() for venue in relevant}
    for a,b in batch:
        peers[a].add(b)
        peers[b].add(a)
    pair_by_id={}
    for row in entries:
        if not isinstance(row,dict):
            continue
        mints=row.get("mints")
        if (not isinstance(mints,list) or len(mints)!=2 or
                not all(isinstance(m,str) and m for m in mints)
                or mints[0]==mints[1]):
            continue
        pair_by_id[(row.get("venue"),row.get("address"))]=tuple(sorted(mints))
    by_venue={}
    for (venue,address),pair in pair_by_id.items():
        by_venue.setdefault(venue,{}).setdefault(pair,set()).add(address)
    from arb.damm_cpmm_atomic_offline import DAMM_POOL, CPMM_POOL
    legacy={"meteora_damm_v2":DAMM_POOL,"raydium_cpmm":CPMM_POOL}
    result={}
    for venue in relevant:
        options=addresses.get(venue,[])
        if not isinstance(options,list):
            raise ValueError("malformed per-venue pool addresses")
        chosen=[legacy[venue]] if venue in legacy and legacy[venue] in options else []
        ranked=[]
        for position,address in enumerate(options):
            if not isinstance(address,str) or address in chosen:
                continue
            pair=pair_by_id.get((venue,address))
            shared=sum(pair in by_venue.get(peer,{}) for peer in peers[venue]) if pair else 0
            ranked.append((-shared,position,address))
        ranked.sort()
        chosen.extend(address for _,_,address in ranked[:maximum-len(chosen)])
        result[venue]=chosen
    return result


def select_distinct_triangle_coverage(candidates, *, maximum=4):
    """Deterministic greedy venue-triple and pair diversity, not first-N duplicates."""
    if type(maximum) is not int or not 1<=maximum<=30:
        raise ValueError("bounded venue coverage required")
    if not isinstance(candidates,list):
        raise ValueError("candidate inventory missing")
    selected=[]
    remaining=list(candidates)
    used_triples=set()
    used_pairs=set()
    while remaining and len(selected)<maximum:
        best=None
        best_score=(-1,-1)
        for index,row in enumerate(remaining):
            venues=row.get("route_venues") if isinstance(row,dict) else None
            if (not isinstance(venues,list) or len(venues)!=3
                    or len(set(venues))!=3):
                raise ValueError("untrusted three-venue candidate")
            triple=frozenset(venues)
            pairs={frozenset((venues[0],venues[1])),
                   frozenset((venues[1],venues[2])),
                   frozenset((venues[2],venues[0]))}
            score=(int(triple not in used_triples),len(pairs-used_pairs))
            if score>best_score:
                best_score=score
                best=index
        selected.append(remaining.pop(best))
        venues=selected[-1]["route_venues"]
        used_triples.add(frozenset(venues))
        used_pairs.update((frozenset((venues[0],venues[1])),
                          frozenset((venues[1],venues[2])),
                          frozenset((venues[2],venues[0]))))
    return selected

def authenticated_distinct_venue_triangles(authenticated_pools, *, limit=30):
    """Discover genuinely closed A→B→C→A three-venue paths from read-only proofs.

    A candidate is only an input to the existing adaptive coordinator: pool
    readback, source fixture hydration, signed CPI and rollback remain unproven.
    """
    if type(limit) is not int or not 1<=limit<=1000:
        raise ValueError("bounded read-only route candidate inventory required")
    if not isinstance(authenticated_pools,dict):
        raise ValueError("authenticated source pool mapping missing")
    edges=[]
    for venue,items in sorted(authenticated_pools.items()):
        if venue not in PROGRAMS or not isinstance(items,list):
            raise ValueError("untrusted authenticated source venue")
        for item in items:
            if (not isinstance(item,dict) or item.get("venue")!=venue
                    or item.get("authenticated") is not True
                    or type(item.get("slot")) is not int or item["slot"]<0
                    or not isinstance(item.get("pool"),str) or not item["pool"]
                    or not isinstance(item.get("mints"),list)
                    or len(item["mints"])!=2 or
                    any(not isinstance(m,str) or not m for m in item["mints"])
                    or item["mints"][0]==item["mints"][1]):
                raise ValueError("untrusted candidate pool identity or source slot")
            for a,b in (item["mints"],item["mints"][::-1]):
                edges.append((a,b,venue,item["pool"],item["slot"]))
    by_input={}
    for edge in edges:
        by_input.setdefault(edge[0],[]).append(edge)
    output=[]
    seen=set()
    for first in edges:
        for second in by_input.get(first[1],[]):
            if second[2]==first[2] or second[1] in (first[0],first[1]):
                continue
            for third in by_input.get(second[1],[]):
                if (third[1]!=first[0] or
                        len({first[2],second[2],third[2]})!=3 or
                        len({first[3],second[3],third[3]})!=3):
                    continue
                identity=((first[2],first[3],first[0],first[1]),
                          (second[2],second[3],second[0],second[1]),
                          (third[2],third[3],third[0],third[1]))
                if identity in seen:
                    continue
                seen.add(identity)
                output.append({
                    "route_venues":[first[2],second[2],third[2]],
                    "route_pool_addresses":[first[3],second[3],third[3]],
                    "route_mints":[first[0],first[1],second[1],first[0]],
                    "source_slots":[first[4],second[4],third[4]],
                    "three_distinct_venues":True,
                    "source_account_fixture_hydrated":False,
                    "signed_atomic_simulation_verified":False,
                    "rollback_failure_case_verified":False,**SAFETY})
                if len(output)>=limit:
                    return output
    return output

def permissioned_dlmm_clock_parity_unverified(activation, *, offline_clock_attested=False):
    """Conservative research-fork gate, not an assertion of mainnet pool status."""
    if not isinstance(activation,dict) or type(activation.get("pair_type")) is not int:
        raise ValueError("authenticated DLMM pair type required")
    if type(offline_clock_attested) is not bool:
        raise ValueError("offline Clock attestation flag must be boolean")
    return activation["pair_type"]==1 and not offline_clock_attested

def probe(rpc, registry, *, batch=BATCH_10, maximum_per_venue=12,
          require_dlmm_swap_eligible=False):
    local_rpc_only(rpc)
    if type(maximum_per_venue) is not int or not 1<=maximum_per_venue<=24:
        raise ValueError("invalid source probe venue budget")
    if type(require_dlmm_swap_eligible) is not bool:
        raise ValueError("invalid DLMM eligibility option")
    entries=prioritized_probe_addresses(registry,candidates(registry),batch,
                                         maximum=maximum_per_venue)
    relevant={v for pair in batch for v in pair}
    pools={}
    failures=[]
    clock=source_clock(rpc) if require_dlmm_swap_eligible else None
    rejected_swap_pools=[]
    for venue in sorted(relevant):
        pools[venue]=[]
        for pool in entries[venue][:maximum_per_venue]:
            try:
                authenticated=snapshot(rpc,pool,venue)
                if require_dlmm_swap_eligible and venue=="meteora_dlmm":
                    from arb.meteora_dlmm import swap_activation_evidence
                    activation=authenticated.get("source_swap_activation")
                    result=swap_activation_evidence(activation,slot=clock["slot"],
                        unix_timestamp=clock["unix_timestamp"])
                    # Permissioned pools enforce Clock-based activation inside
                    # the deployed swap. Source Clock is authenticated here,
                    # but the source-disconnected offline Surfpool does not
                    # attest that its Clock matches that source snapshot.
                    # Never infer offline execution readiness from source time.
                    if permissioned_dlmm_clock_parity_unverified(activation):
                        rejected_swap_pools.append({"venue":venue,"pool":pool,
                            "reason":"PERMISSIONED_DLMM_OFFLINE_CLOCK_PARITY_UNVERIFIED",
                            "source_swap_activation":result})
                        continue
                    if not result["swap_eligible"]:
                        rejected_swap_pools.append({"venue":venue,"pool":pool,
                            "reason":result["reason"],
                            "source_swap_activation":result})
                        continue
                    authenticated["source_swap_eligibility"]=result
                pools[venue].append(authenticated)
            except (ValueError,KeyError,TypeError) as exc:
                failures.append({"venue":venue,"pool":pool,
                                 "error_class":type(exc).__name__,
                                 "diagnostic":str(exc)[:120]})
    routes=[]
    for first,second in batch:
        combinations=[]
        for a in pools[first]:
            for b in pools[second]:
                if set(a["mints"])==set(b["mints"]):
                    combinations.append({"first_pool":a["pool"],
                                         "second_pool":b["pool"],
                                         "mint_pair":a["mints"],
                                         "first_slot":a["slot"],
                                         "second_slot":b["slot"]})
        routes.append({"first_venue":first,"second_venue":second,
                       "authenticated_pool_pair_candidates":combinations[:10],
                       "candidate_count":len(combinations),
                       "signed_atomic_simulation_verified":False,
                       "rollback_failure_case_verified":False,**SAFETY})
    triangles=select_distinct_triangle_coverage(authenticated_distinct_venue_triangles(pools,limit=100),maximum=30)
    return {"status":"READONLY_NEXT_TEN_FORK_POOL_AUTHENTICATION",
            "authenticated_distinct_venue_three_leg_candidates":triangles,
            "authenticated_distinct_venue_three_leg_candidate_count":len(triangles),
            "source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "route_count":len(routes),"authenticated_pools":pools,
            "route_candidates":routes,"failed_pool_checks":failures,
            "source_swap_eligibility_rejections":rejected_swap_pools,
            "source_clock_for_swap_gate":clock,
            "signed_atomic_simulation_verified":False,**SAFETY}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--output",required=True)
    p.add_argument("--batch",choices=("first","next","remaining","non-v4"),default="first")
    p.add_argument("--only-venue",choices=("raydium_amm_v4",))
    args=p.parse_args()
    report=probe(args.rpc,json.loads(Path(args.registry).read_text()),batch=tuple(pair for pair in route_batch(args.batch) if not args.only_venue or args.only_venue in pair))
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "routes_with_authenticated_candidates":sum(
                        x["candidate_count"]>0 for x in report["route_candidates"]),
                      "signed_atomic_simulation_verified":False,"broadcast":False}))
if __name__=="__main__":
    main()
