"""Capture genuine authenticated 4–6-hop source routes, without signing.

Reuses the existing per-venue account exporter and upstream-backed local fork.
One contextual RPC call binds all legs to a shared source slot. This is source
evidence only, NOT signed execution or a protocol-exact quote.
"""
import base64,json
from pathlib import Path
from arb.next_ten_pair_fixture_export import venue_accounts,program_data_accounts
from arb.next_ten_fork_pool_probe import PROGRAMS,DECODERS,MINT_KEYS,snapshot
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.source_snapshot_manifest import digest,verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def capture(rpc,graph,route_index,output,*,venue_cache=None):
    local_rpc_only(rpc)
    if (not isinstance(graph,dict) or
            graph.get("status")!="SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY"
            or any(graph.get(k)is not False for k in SAFE)
            or type(route_index)is not int or route_index<0):
        raise ValueError("safe authenticated graph and index required")
    routes=graph.get("routes")
    if not isinstance(routes,list) or route_index>=len(routes):
        raise ValueError("source graph route absent")
    route=routes[route_index]
    legs=route.get("legs")
    if not isinstance(legs,list) or not 3<=len(legs)<=6 or route.get("hops")!=len(legs):
        raise ValueError("four to six source hops required")
    if venue_cache is not None and not isinstance(venue_cache,dict):
        raise ValueError("source venue cache must be a per-fork mapping")
    current=route.get("start_mint")
    mints=[current]
    addresses=[]
    evidence=[]
    for leg in legs:
        venue,pool=leg.get("venue"),leg.get("pool")
        if (venue not in PROGRAMS or not isinstance(pool,str) or not pool or
                leg.get("input")!=current or not isinstance(leg.get("output"),str)):
            raise ValueError("source graph mint/venue continuity absent")
        # Account evidence can be direction-specific (notably Orca tick arrays).
        # Never reuse a pool's forward evidence for its reverse swap.
        cache_key=(venue,pool,current,leg["output"])
        cached=venue_cache.get(cache_key) if venue_cache is not None else None
        if cached is None:
            proof=snapshot(rpc,pool,venue)
            extra,aux=venue_accounts(rpc,venue,pool,[current,leg["output"]],directional_only=True)
            if venue_cache is not None:
                venue_cache[cache_key]=(proof,tuple(extra),aux)
        else:
            proof,extra,aux=cached
        if (proof.get("authenticated") is not True or
                set(proof.get("mints",[]))!={current,leg["output"]}):
            raise ValueError("source pool reauthentication failed")
        addresses.extend(extra)
        evidence.append({"venue":venue,"pool":pool,"source_slot":proof["slot"],"auxiliary":aux})
        current=leg["output"]
        mints.append(current)
    if current!=mints[0] or len({leg["pool"] for leg in legs})!=len(legs):
        raise ValueError("four-to-six route must be closed with distinct pools")
    addresses=list(dict.fromkeys(addresses))
    if not addresses or len(addresses)>100:
        raise ValueError("source auxiliary inventory exceeds getMultipleAccounts 100-key limit")
    response=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    values=response.get("value")
    if (type(slot)is not int or slot<0 or not isinstance(values,list) or
            len(values)!=len(addresses)):
        raise ValueError("single-slot multi-hop source response malformed")
    missing=[address for address,value in zip(addresses,values) if value is None]
    if missing:
        # An absent source account is not an offline permission to fabricate
        # it. Preserve bounded identities and roles for reproducible triage.
        roles={}
        for leg,proof in zip(legs,evidence):
            identity=(leg["venue"],leg["pool"])
            roles.setdefault(leg["pool"],[]).append(identity+("pool",))
            aux=proof["auxiliary"]
            for key in ("tick_arrays","bin_arrays"):
                for address in aux.get(key,[]) if isinstance(aux,dict) else []:
                    roles.setdefault(address,[]).append(identity+(key,))
        detail=[{"address":address,"roles":roles.get(address,[])[:3]}
                for address in missing[:6]]
        raise ValueError("single-slot missing required source accounts: "+
                         json.dumps({"total":len(missing),"first":detail},
                                    separators=(",",":")))
    if any(not isinstance(value,dict) for value in values):
        raise ValueError("single-slot multi-hop source account data invalid")
    accounts=dict(zip(addresses,values))
    for i,leg in enumerate(legs):
        account=accounts[leg["pool"]]
        venue=leg["venue"]
        if account.get("owner")!=PROGRAMS[venue] or account.get("executable") is not False:
            raise ValueError("source pool changed owner within contextual capture")
        raw=account.get("data")
        if not isinstance(raw,list) or len(raw)!=2 or raw[1]!="base64":
            raise ValueError("source pool bytes unavailable")
        state=DECODERS[venue](base64.b64decode(raw[0],validate=True))
        if set(state[k] for k in MINT_KEYS[venue])!={mints[i],mints[i+1]}:
            raise ValueError("source pool changed mint identity")
        if venue=="meteora_dlmm":
            directional=evidence[i]["auxiliary"].get("directional_bin_source")
            if directional is not None:
                from arb.meteora_dlmm_bin_preflight import (
                    active_bin_array_index,verify_directional_bin_snapshot)
                # Reject clock drift between the preliminary authenticated
                # pool bytes and this ONE-SLOT account snapshot, even if the
                # PDA at the old index still exists.
                if (active_bin_array_index(state["active_id"])!=
                        directional["active_bin_array_index"]):
                    raise ValueError("DLMM active bin shifted across source snapshot")
                verify_directional_bin_snapshot(leg["pool"],directional,accounts)
    programs={PROGRAMS[l["venue"]] for l in legs}
    if any(l["venue"]=="pumpswap" for l in legs):
        from arb.pumpswap_fee_account import PROGRAM as FEE
        programs.add(FEE)
    accounts.update(program_data_accounts(rpc,programs))
    result={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
            "fixture_kind":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE",
            "route_venues":[l["venue"] for l in legs],
            "route_pool_addresses":[l["pool"] for l in legs],
            "route_mints":mints,"leg_evidence_by_index":evidence,
            "state_accounts_observed_slot":slot,
            "state_account_count":len(addresses),"state_account_addresses":addresses,
            "state_account_manifest_sha256":digest(accounts,addresses,slot),
            "accounts":accounts,"signed_atomic_simulation_verified":False,
            "rollback_failure_case_verified":False,**SAFE}
    verify(result)
    Path(output).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return {"status":"AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_FIXTURE",
            "hops":len(legs),"source_slot":slot,"state_account_count":len(addresses),**SAFE}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--graph",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--report",required=True)
    args=p.parse_args()
    graph=json.loads(Path(args.graph).read_text())
    targets=[i for i,r in enumerate(graph.get("routes",[]))
             if 3<=r.get("hops",0)<=6]
    result={"status":"NO_AUTHENTICATED_FOUR_TO_SIX_CYCLE",**SAFE}
    failures=[]
    # A candidate graph is not an authenticated fixture. If the first
    # candidate has an unavailable pool, continue to the next independent
    # candidate rather than denying the signer a real multi-hop source.
    for index in targets[:8]:
        try:
            captured=capture(args.rpc,graph,index,args.output)
            result={**captured,"graph_route_index":index,
                    "candidate_capture_attempts":len(failures)+1,
                    "previous_candidate_failures":failures}
            break
        except (ValueError,TypeError,KeyError,RuntimeError) as exc:
            failures.append({"graph_route_index":index,
                             "reason":str(exc)[:240]})
    else:
        if targets:
            result={"status":"SOURCE_CAPTURE_BLOCKED",
                    "candidate_capture_attempts":len(failures),
                    "remaining_candidates_untried":max(0,len(targets)-len(failures)),
                    "candidate_failures":failures,**SAFE}
    Path(args.report).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))
if __name__=="__main__":main()
