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

def decode_source_clock_account(info):
    """Decode the original Clock account for read-only pricing provenance."""
    if (not isinstance(info,dict)
            or info.get("owner")!="Sysvar1111111111111111111111111111111111111"
            or info.get("executable") is not False):
        raise ValueError("source Clock sysvar absent or owner mismatch")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("source Clock sysvar encoding mismatch")
    raw=base64.b64decode(data[0],validate=True)
    if len(raw)!=40:
        raise ValueError("source Clock sysvar length mismatch")
    slot=int.from_bytes(raw[0:8],"little")
    unix_timestamp=int.from_bytes(raw[32:40],"little",signed=True)
    if unix_timestamp<0:
        raise ValueError("negative source Clock timestamp")
    return {"slot":slot,"unix_timestamp":unix_timestamp}


def source_clock(rpc):
    """Read source-fork Clock sysvar; never use wall clock as protocol evidence."""
    info=call(rpc,"getAccountInfo",[CLOCK_SYSVAR,
        {"encoding":"base64","commitment":"confirmed"}]).get("value")
    return decode_source_clock_account(info)


def contextual_route_clock(fixture,*,allow_one_slot_ahead_model=False):
    """Recompute contextual Clock from retained bytes, never hydrate a sysvar.

    Historical fixtures and explicit unavailable observations have no exact
    context Clock. A malformed present record is not silently downgraded.
    """
    if type(allow_one_slot_ahead_model) is not bool:
        raise ValueError("explicit near-context clock model opt-in required")
    proof=fixture.get("contextual_source_clock")
    if proof is None:
        return None
    if (not isinstance(proof,dict)
            or proof.get("address")!=CLOCK_SYSVAR
            or proof.get("context_slot")!=fixture.get("state_accounts_observed_slot")
            or any(proof.get(k) is not False for k in SAFETY)):
        raise ValueError("source Clock context identity mismatch")
    if (CLOCK_SYSVAR in fixture["accounts"]
            or CLOCK_SYSVAR in fixture["state_account_addresses"]):
        raise ValueError("source Clock must not be hydrated")
    if proof.get("status")=="SOURCE_CONTEXT_CLOCK_UNAVAILABLE":
        if proof.get("account") is not None:
            raise ValueError("unavailable source Clock has account bytes")
        return None
    clock=decode_source_clock_account(proof["account"])
    expected="SOURCE_CONTEXT_CLOCK_MATCHED" if clock["slot"]==proof["context_slot"] else "SOURCE_CONTEXT_CLOCK_SLOT_DIVERGED"
    if proof.get("status")!=expected or proof.get("decoded")!=clock:
        raise ValueError("source Clock claim differs from retained account")
    if expected=="SOURCE_CONTEXT_CLOCK_MATCHED":
        return clock
    # The current source fork reports Clock.slot=context+1 in the SAME
    # response. Model that observation without pretending it matches the
    # context slot, or altering either source account or clock.
    if allow_one_slot_ahead_model and clock["slot"]==proof["context_slot"]+1:
        return clock
    return None


def contextual_pricing_clock(fixture):
    clock=contextual_route_clock(fixture,allow_one_slot_ahead_model=True)
    if clock is None:
        return None
    delta=clock["slot"]-fixture["state_accounts_observed_slot"]
    return {"clock":clock,"source_slot":fixture["state_accounts_observed_slot"],
        "clock_slot_delta":delta,"same_slot_attested":delta==0,
        "provenance":("CONTEXTUAL_SOURCE_CLOCK_MATCHED" if delta==0
                       else "CONTEXTUAL_SOURCE_CLOCK_ONE_SLOT_AHEAD_MODEL"),
        **SAFETY}


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

def prioritized_probe_addresses(registry, addresses, batch, *, maximum=12,
                                prefer_start_mint_coverage=False,historical_recovery=False):
    """Prioritize *hinted* cross-venue pair overlap before source RPC reads.

    This is scheduling ONLY. Mint labels in registry cannot authenticate any
    pool, and snapshot() still independently checks the actual program owner,
    decoder, mint identity and reserves before route consideration.
    """
    if maximum is not None and (type(maximum) is not int or not 1<=maximum<=48):
        raise ValueError("bounded paired source pool probes required")
    if (type(prefer_start_mint_coverage) is not bool or type(historical_recovery) is not bool
            or historical_recovery and not prefer_start_mint_coverage):
        raise ValueError("invalid three-hop token coverage policy")
    entries=registry.get("pools") if isinstance(registry,dict) else None
    if not isinstance(entries,list) or not isinstance(addresses,dict):
        raise ValueError("malformed pool probe inventory")
    relevant={venue for route in batch for venue in route}
    if maximum is None:
        result={}
        for venue in sorted(relevant):
            options=addresses.get(venue,[])
            if not isinstance(options,list) or any(not isinstance(p,str) or not p for p in options):
                raise ValueError("malformed full source pool inventory")
            result[venue]=list(dict.fromkeys(options))
        return result
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
    covered={}
    if prefer_start_mint_coverage:
        from arb.m5_start_mint_expansion import starting_mint_coverage_pool_subset
        covered=starting_mint_coverage_pool_subset(entries,
            maximum_per_venue=maximum,target_start_mints=100,
            historical_recovery=historical_recovery)["addresses"]
    result={}
    for venue in relevant:
        options=addresses.get(venue,[])
        if not isinstance(options,list):
            raise ValueError("malformed per-venue pool addresses")
        chosen=[p for p in covered.get(venue,[]) if p in options]
        if len(chosen)<maximum and venue in legacy and legacy[venue] in options and legacy[venue] not in chosen:
            chosen.append(legacy[venue])
        if prefer_start_mint_coverage:
            # Spend source RPC only on pools needed for distinct triangle
            # coverage. Existing addresses still require snapshot() readback.
            result[venue]=chosen
            continue
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
    by_direction={}
    for edge in edges:
        by_direction.setdefault((edge[0],edge[1]),[]).append(edge)
    output=[]
    seen=set()
    for first in edges:
        for second in by_input.get(first[1],[]):
            if second[2]==first[2] or second[1] in (first[0],first[1]):
                continue
            for third in by_direction.get((second[1],first[0]),[]):
                if (len({first[2],second[2],third[2]})!=3 or
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
          require_dlmm_swap_eligible=False,prefer_start_mint_coverage=False,
          historical_recovery=False):
    local_rpc_only(rpc)
    if maximum_per_venue is not None and (type(maximum_per_venue) is not int
            or not 1<=maximum_per_venue<=48):
        raise ValueError("invalid source probe venue budget")
    if type(require_dlmm_swap_eligible) is not bool:
        raise ValueError("invalid DLMM eligibility option")
    if type(prefer_start_mint_coverage) is not bool:
        raise ValueError("invalid source start-mint coverage option")
    entries=prioritized_probe_addresses(registry,candidates(registry),batch,
                                         maximum=maximum_per_venue,
                                         prefer_start_mint_coverage=prefer_start_mint_coverage,
                                         historical_recovery=historical_recovery)
    if maximum_per_venue is not None and sum(map(len,entries.values()))>200:
        raise ValueError("source pool graph exceeds 200 identities; tighten token-diverse selection")
    relevant={v for pair in batch for v in pair}
    pools={}
    failures=[]
    clock=source_clock(rpc) if require_dlmm_swap_eligible else None
    rejected_swap_pools=[]
    for venue in sorted(relevant):
        pools[venue]=[]
        for pool in entries[venue]:
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
                    if permissioned_dlmm_clock_parity_unverified(activation) and activation["activation_type"]!=0:
                        rejected_swap_pools.append({"venue":venue,"pool":pool,
                            "reason":"PERMISSIONED_DLMM_TIMESTAMP_CLOCK_PARITY_UNVERIFIED",
                            "source_swap_activation":result})
                        continue
                    if not result["swap_eligible"]:
                        rejected_swap_pools.append({"venue":venue,"pool":pool,
                            "reason":result["reason"],
                            "source_swap_activation":result})
                        continue
                    authenticated["source_swap_eligibility"]=result
                    if activation["pair_type"]==1:
                        authenticated["offline_slot_alignment_required"]=True
                pools[venue].append(authenticated)
            except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
                failures.append({"venue":venue,"pool":pool,
                                 "error_class":type(exc).__name__,
                                 "diagnostic":str(exc)[:120]})
    # Count all pair candidates without materializing the Cartesian
    # product of large parallel-pool sets. The ten samples are diagnostic.
    pairs_by_venue={}
    for venue,records in pools.items():
        by_pair={}
        for row in records:
            by_pair.setdefault(tuple(sorted(row["mints"])),[]).append(row)
        pairs_by_venue[venue]=by_pair
    routes=[]
    for first,second in batch:
        combinations=[]
        candidate_count=0
        for a in pools[first]:
            matches=pairs_by_venue[second].get(tuple(sorted(a["mints"])),[])
            candidate_count+=len(matches)
            for b in matches[:max(0,10-len(combinations))]:
                combinations.append({"first_pool":a["pool"],
                                     "second_pool":b["pool"],
                                     "mint_pair":a["mints"],
                                     "first_slot":a["slot"],
                                     "second_slot":b["slot"]})
        routes.append({"first_venue":first,"second_venue":second,
                       "authenticated_pool_pair_candidates":combinations,
                       "candidate_count":candidate_count,
                       "signed_atomic_simulation_verified":False,
                       "rollback_failure_case_verified":False,**SAFETY})
    triangles=select_distinct_triangle_coverage(authenticated_distinct_venue_triangles(pools,limit=100),maximum=30)
    return {"status":"READONLY_NEXT_TEN_FORK_POOL_AUTHENTICATION",
            "authenticated_distinct_venue_three_leg_candidates":triangles,
            "authenticated_distinct_venue_three_leg_candidate_count":len(triangles),
            "source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "route_count":len(routes),"authenticated_pools":pools,
            "source_pool_count_limit":None if maximum_per_venue is None else 200,
            "source_pool_per_venue_limit":maximum_per_venue,
            "source_pool_attempts_by_venue":{v:len(entries[v]) for v in sorted(relevant)},
            "all_selected_pool_hints_attempted":True,
            "source_authenticated_pool_counts_by_venue":{v:len(rows) for v,rows in pools.items()},
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
