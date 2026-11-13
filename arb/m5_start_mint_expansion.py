"""Topology-driven, read-only pool discovery to maximize distinct three-hop start mints.

The registry is a source hint, not proof of executable liquidity. Suggestions
become candidate edges only after source-RPC program and reserve verification.
This scout never signs, hydrates, trades, or marks routes profitable.
"""
import argparse,json
from collections import defaultdict
from pathlib import Path
from arb.onchain_pool_discovery import discover
from arb.orca_whirlpool import SOL,USDC

USDT="Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
HUBS=(SOL,USDC,USDT)
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
DEFAULT_VENUES=("orca","raydium_cpmm","meteora_damm_v2","raydium_clmm")

def topology(entries):
    if not isinstance(entries,list):
        raise ValueError("pool registry rows required")
    by_mint=defaultdict(list)
    seen=set()
    for p in entries:
        if not isinstance(p,dict):
            raise ValueError("malformed pool entry")
        venue,address,mints=p.get("venue"),p.get("address"),p.get("mints")
        if not isinstance(venue,str) or not isinstance(address,str) or not address or (
            not isinstance(mints,list) or len(mints)!=2 or
            any(not isinstance(m,str) or not m for m in mints) or mints[0]==mints[1]):
            raise ValueError("malformed pool identity")
        if (venue,address) in seen:
            raise ValueError("duplicate pool identity")
        seen.add((venue,address))
        for mint in mints:by_mint[mint].append(p)
    cyclic=set()
    for start,first_edges in by_mint.items():
        for a in first_edges:
            middle=a["mints"][0] if a["mints"][1]==start else a["mints"][1]
            for b in by_mint[middle]:
                if b["address"]==a["address"] and b["venue"]==a["venue"]:continue
                last=b["mints"][0] if b["mints"][1]==middle else b["mints"][1]
                if last==start or last==middle:continue
                for c in by_mint[last]:
                    if start not in c["mints"]:continue
                    ids={(x["venue"],x["address"]) for x in (a,b,c)}
                    if len(ids)==3:
                        cyclic.add(start)
                        break
                if start in cyclic:break
            if start in cyclic:break
    return {"distinct_mints":len(by_mint),"three_hop_start_mints":sorted(cyclic),
            "three_hop_start_mint_count":len(cyclic),
            "mint_neighbors":{m:sorted({p["mints"][0] if p["mints"][1]==m else p["mints"][1]
                for p in edges}) for m,edges in by_mint.items()}}

def bridge_targets(entries, *, maximum=360):
    if type(maximum)is not int or not 1<=maximum<=360:
        raise ValueError("bounded discovery target budget required")
    graph=topology(entries)
    existing=graph["three_hop_start_mints"]
    count=defaultdict(int)
    current_pairs=set()
    for p in entries:
        current_pairs.add(tuple(sorted(p["mints"])))
        for m in p["mints"]:count[m]+=1
    candidates=[]
    for mint,neighbors in graph["mint_neighbors"].items():
        if mint in existing or mint in HUBS:
            continue
        # A token can already have non-hub neighbors and still lack a closed
        # triangle. Do not discard it just because its graph degree exceeds 1.
        # A missing second hub connection is a *candidate* bridge only when
        # an existing edge joins that hub to one of its connected hubs.
        # Hub-backed triangles are a discovery scaffold, not a requirement
        # that the existing second leg also be a hub. Any authenticated
        # neighbor with an existing connection to the target hub can close
        # mint -> neighbor -> hub -> mint. This captures non-leaf tokens
        # that would otherwise be stranded by hub-only bridge scheduling.
        for target in HUBS:
            if target in neighbors or tuple(sorted((mint,target))) in current_pairs:
                continue
            old=next((neighbor for neighbor in neighbors
                      if tuple(sorted((neighbor,target))) in current_pairs),None)
            if old is None:
                continue
            candidates.append({"mint":mint,"connected_hub":old,"missing_hub":target,
                               "pair":[mint,target],"current_pools":count[mint]})
    # Prefer established tokens with multiple authenticated pool identity hints.
    # Keep alternative missing-hub options together and balance per token.
    candidates.sort(key=lambda x:(-x["current_pools"],x["mint"],x["missing_hub"]))
    # Search both missing liquid hubs when possible. The first may have no
    # Whirlpool while the second does; do not artificially cap discovery at
    # one hub per mint. Keep deterministic priority and per-mint balance.
    by_token=defaultdict(list)
    for row in candidates:by_token[row["mint"]].append(row)
    result=[]
    for pass_index in range(2):
        for mint in sorted(by_token,key=lambda m:(-count[m],m)):
            possibilities=by_token[mint]
            if pass_index<len(possibilities):
                result.append(possibilities[pass_index])
                if len(result)>=maximum:break
        if len(result)>=maximum:break
    return {"topology":graph,"targets":result,
            "targets_are_unverified_hints":True,**SAFE}

def starting_mint_coverage_pool_subset(entries, *, maximum_per_venue=24,
                                       target_start_mints=100):
    """Choose registry HINT addresses covering true 3-hop token triangles.

    Never authenticates these hints. The caller MUST revalidate each selected
    source account before route construction, and signed simulation still gates
    the final starting-token count.
    """
    from itertools import product
    if (type(maximum_per_venue)is not int or not 1<=maximum_per_venue<=48 or
            type(target_start_mints)is not int or not 1<=target_start_mints<=100):
        raise ValueError("bounded triangle coverage targets required")
    graph=topology(entries)
    pool_by_pair=defaultdict(list)
    adjacency=defaultdict(set)
    for row in entries:
        a,b=row["mints"]
        pool_by_pair[tuple(sorted((a,b)))].append(row)
        adjacency[a].add(b)
        adjacency[b].add(a)
    triples=[]
    for a in sorted(adjacency):
        for b in sorted(n for n in adjacency[a] if n>a):
            for c in sorted(n for n in adjacency[b] if n>b and n in adjacency[a]):
                edges=[pool_by_pair[tuple(sorted(edge))] for edge in
                       ((a,b),(b,c),(c,a))]
                triples.append(((a,b,c),edges))
    # Rare starting tokens are easier to lose under venue/pool budgets.
    # Prefer triangles containing fewer alternative paths before spending
    # scarce source-probe slots on hubs with hundreds of alternatives.
    frequency=defaultdict(int)
    for tokens,_ in triples:
        for mint in tokens:frequency[mint]+=1
    chosen={}
    counts=defaultdict(int)
    covered=set()
    while len(covered)<target_start_mints:
        best=None
        best_score=None
        for tokens,edges in triples:
            new_mints=sum(t not in covered for t in tokens)
            if not new_mints:continue
            # Preserve alternative venues in each pair's candidate budget:
            # a straight first-six pool slice can all belong to an exhausted
            # venue and hide a valid triangle in another authenticated venue.
            options=[]
            for poolset in edges:
                by_venue=defaultdict(list)
                for p in sorted(poolset,key=lambda p:(
                        (p["venue"],p["address"]) not in chosen,
                        counts[p["venue"]],p["venue"],p["address"])):
                    if len(by_venue[p["venue"]])<2:
                        by_venue[p["venue"]].append(p)
                # Round-robin venues before taking second identities, so
                # the bounded combinatorial search stays cheap and diverse.
                options.append([p for offset in range(2)
                                for venue in sorted(by_venue)
                                if len(by_venue[venue])>offset
                                for p in by_venue[venue][offset:offset+1]][:8])
            for candidate in product(*options):
                identities={(p["venue"],p["address"]) for p in candidate}
                if len(identities)!=3:continue
                additions=[p for p in candidate if (p["venue"],p["address"]) not in chosen]
                increments=defaultdict(int)
                for row in additions:increments[row["venue"]]+=1
                if (any(counts[v]+inc>maximum_per_venue for v,inc in increments.items())
                        or sum(counts.values())+len(additions)>200):
                    continue
                # First maximize distinct reachable starts, then protect
                # scarce starts with few remaining triangle alternatives.
                rarity=sum(1/frequency[t] for t in tokens if t not in covered)
                score=(new_mints,rarity,-len(additions),
                       -sum(counts[p["venue"]] for p in candidate))
                if best_score is None or score>best_score:
                    best_score=score
                    best=(tokens,candidate,additions)
        if best is None:break
        tokens,candidate,additions=best
        for row in additions:
            chosen[(row["venue"],row["address"])]=row
            counts[row["venue"]]+=1
        covered.update(tokens)
    selected=defaultdict(list)
    for (venue,address),row in chosen.items():
        selected[venue].append(address)
    return {"addresses":{venue:sorted(addresses) for venue,addresses in selected.items()},
            "three_hop_mint_topology_ceiling":graph["three_hop_start_mint_count"],
            "selected_three_hop_start_mint_count":len(covered),
            "selected_three_hop_start_mints":sorted(covered),
            "unselected_topology_start_mints":sorted(set(graph["three_hop_start_mints"])-covered),
            "selected_pool_identity_count":len(chosen),
            "selection_policy":"SCARCITY_WEIGHTED_DISTINCT_START_TRIANGLES_VENUE_DIVERSE_200_POOL_CAP",
            "source_authenticated":False,
            "signed_simulation_verified":False,
            **SAFE}

def derive_orca_bridge_addresses(rpc,entries,targets,*,spacings=(1,2,4,8,16,32,64,128,256)):
    """Derive Whirlpool PDAs using source-fetched config keys; no GPA scans.

    Unoccupied PDA addresses are not pools. Each non-null candidate must
    re-authenticate program ownership, mint identity, and vault state.
    """
    import base64
    from solders.pubkey import Pubkey
    from arb.rpc import call
    from arb.orca_whirlpool import PROGRAM as ORCA,SIZE as ORCA_SIZE,DISCRIMINATOR
    from arb.onchain_pool_discovery import verify as verify_pool
    from arb.orca_whirlpool import decode as decode_orca
    if (not isinstance(targets,list) or len(targets)>360 or
            any(type(t.get("mint"))is not str or type(t.get("missing_hub"))is not str
                for t in targets)):
        raise ValueError("bounded trusted bridge target hints required")
    if (not isinstance(spacings,tuple) or not spacings or
            any(type(x)is not int or not 1<=x<=32767 for x in spacings)):
        raise ValueError("invalid bounded Whirlpool spacing candidates")
    sources=[p["address"] for p in entries if p["venue"]=="orca"][:24]
    if not sources:
        raise ValueError("no existing Orca pool config sources")
    response=call(rpc,"getMultipleAccounts",[sources,{"encoding":"base64","commitment":"confirmed"}])
    configs=set()
    for address,info in zip(sources,response.get("value") or []):
        if not info or info.get("owner")!=ORCA:
            continue
        raw=base64.b64decode(info["data"][0],validate=True)
        if len(raw)!=ORCA_SIZE or raw[:8]!=DISCRIMINATOR:continue
        configs.add(raw[8:40])
    if not configs:raise ValueError("no authenticated Whirlpool config candidates")
    if len(configs)>8:raise ValueError("too many Whirlpool source configurations")
    program=Pubkey.from_string(ORCA)
    candidates={}
    for target in targets:
        a,b=sorted((Pubkey.from_string(target["mint"]),Pubkey.from_string(target["missing_hub"])),key=bytes)
        for config in sorted(configs):
            for spacing in spacings:
                address=str(Pubkey.find_program_address(
                    [b"whirlpool",config,bytes(a),bytes(b),spacing.to_bytes(2,"little")],program)[0])
                candidates[address]={"target":target,"spacing":spacing}
    verified=[]
    errors=[]
    keys=list(candidates)
    for start in range(0,len(keys),100):
        batch=keys[start:start+100]
        data=call(rpc,"getMultipleAccounts",[batch,{"encoding":"base64","commitment":"confirmed"}])
        values=data.get("value")
        if not isinstance(values,list) or len(values)!=len(batch):
            raise ValueError("missing direct Whirlpool PDA account read")
        for address,info in zip(batch,values):
            if info is None:continue
            try:
                if info.get("owner")!=ORCA or info.get("executable"):
                    raise ValueError("derived Whirlpool PDA owner mismatch")
                raw=base64.b64decode(info["data"][0],validate=True)
                state=decode_orca(raw)
                pair=set((candidates[address]["target"]["mint"],
                          candidates[address]["target"]["missing_hub"]))
                if {state["token_mint_a"],state["token_mint_b"]}!=pair:
                    raise ValueError("derived Whirlpool mint identity mismatch")
                pool=verify_pool(rpc,"orca",address,state)
                verified.append(pool)
            except (ValueError,TypeError,KeyError,RuntimeError) as exc:
                errors.append({"address":address,"error":str(exc)[:160]})
    return {"source_verified_pools":verified,"candidate_pd_as_checked":len(keys),
            "source_whirlpool_config_count":len(configs),"candidate_tick_spacings":list(spacings),"authentication_errors":errors}



def missing_triangle_edge_targets(entries, *, maximum=360):
    """Rank missing edges that would close a three-pool cycle for a new mint.

    Unlike hub-only bridge hints, any genuine two-edge path A-B-C can
    motivate a bounded search for A-C. These are UNVERIFIED pool hints;
    only source-authenticated search and subsequent graph reprobe count.
    """
    if type(maximum)is not int or not 1<=maximum<=360:
        raise ValueError("invalid missing-edge search budget")
    graph=topology(entries)
    existing=set(graph["three_hop_start_mints"])
    neighbors={mint:set(other) for mint,other in graph["mint_neighbors"].items()}
    pairs={}
    for mint in sorted(neighbors):
        if mint in existing:
            continue
        for intermediate in sorted(neighbors[mint]):
            for last in sorted(neighbors[intermediate]):
                if last==mint or last in neighbors[mint]:
                    continue
                pair=tuple(sorted((mint,last)))
                # Require a real two-edge path, never count a missing edge
                # itself as a pool, quote, or profitable opportunity.
                proposal={"mint":mint,"connected_neighbor":intermediate,
                          "missing_neighbor":last,"pair":list(pair),
                          "closes_new_start":True}
                score=(last in HUBS,intermediate in HUBS,
                       len(neighbors[mint]),len(neighbors[last]))
                old=pairs.get(pair)
                if old is None or score>old[0]:
                    pairs[pair]=(score,proposal)
    ranked=sorted(pairs.values(),key=lambda item:(
        -int(item[0][0]),-int(item[0][1]),-item[0][2],-item[0][3],
        item[1]["pair"]))
    return {"status":"MISSING_TRIANGLE_EDGE_HINTS_NOT_SOURCE_VERIFIED",
            "missing_edge_pair_count":len(ranked),
            "targets":[item[1] for item in ranked[:maximum]],
            "truncated":len(ranked)>maximum,
            "source_authenticated":False,
            "signed_simulation_verified":False,**SAFE}



def discover_on_separate_rpc(source_rpc, discovery_rpc, pairs, venues, *,
                             search_fn=None, verify_fn=None):
    """Search on a separate provider, reauthenticate EVERY pool on source fork.

    External GPA search data is an untrusted address hint. Never substitute
    external balances, slot, or state for source-fork evidence.
    """
    from arb.onchain_pool_discovery import search_pair,verify
    search_fn=search_fn or search_pair
    verify_fn=verify_fn or verify
    rows=[]
    errors=[]
    attempted=0
    throttled=False
    for pair in pairs:
        for venue in venues:
            if throttled:
                break
            attempted+=1
            try:
                found=search_fn(discovery_rpc,venue,*pair,limit=8,
                                pace_seconds=0.5)
            except (ValueError,RuntimeError,OSError,TypeError,KeyError) as exc:
                # HTTP errors sometimes contain the provider URL, including
                # API-key query parameters. Never serialize exception text.
                message=str(exc).lower()
                limited=("429" in message or "too many requests" in message
                         or "rate limit" in message)
                errors.append({"venue":venue,"pair":list(pair),
                               "error":"DISCOVERY_PROVIDER_RATE_LIMITED" if limited
                                       else "DISCOVERY_PROVIDER_QUERY_FAILED",
                               "exception_class":type(exc).__name__})
                if limited:
                    throttled=True
                continue
            if not isinstance(found,dict):
                raise ValueError("invalid alternate discovery account inventory")
            for address,state in found.items():
                try:
                    if not isinstance(address,str) or not address:
                        raise ValueError("invalid discovered pool address")
                    # Independently fetch the account and its vaults from the
                    # source-backed fork. The verifier compares decoded pool
                    # state, owner and mints at a source context slot.
                    verified=verify_fn(source_rpc,venue,address,state)
                    if (not isinstance(verified,dict) or
                            verified.get("venue")!=venue or
                            verified.get("address")!=address or
                            type(verified.get("slot")) is not int or
                            verified["slot"]<0 or
                            sorted(verified.get("mints",[]))!=list(pair) or
                            verified.get("swap_simulated") is not False):
                        raise ValueError("source-verified pool identity mismatch")
                    rows.append(verified)
                except (ValueError,RuntimeError,TypeError,KeyError,OSError) as exc:
                    # Keep verification failures inspectable without
                    # leaking upstream provider URLs in raw exceptions.
                    errors.append({"venue":venue,"address":address,
                                   "error":"SOURCE_REAUTHENTICATION_FAILED",
                                   "exception_class":type(exc).__name__})
        if throttled:
            break
    return {"status":"UPSTREAM_RATE_LIMITED" if throttled else (
                "PARTIAL" if errors else "COMPLETE"),
            "pools":rows,"errors":errors,
            "searched_venue_pairs":attempted,
            "verification_rpc":"LOCAL_SOURCE_FORK",
            "discovery_rpc":"SEPARATE_UNTRUSTED_PROVIDER",
            **SAFE}


def multi_venue_bridge_scout(rpc, entries, *, maximum_pairs=12,
                             venues=("raydium_cpmm","meteora_damm_v2"),
                             discover_fn=None,discovery_rpc=None):
    """Search distinct missing triangle edges and independently verify pools.

    getProgramAccounts may be rate limited. Any returned identity must be
    source-verified by the venue verifier and match a requested pair exactly.
    Hints and failed RPC requests are never included as verified pools.
    """
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.onchain_pool_discovery import discover,VENUES
    local_rpc_only(rpc)
    if (type(maximum_pairs)is not int or not 1<=maximum_pairs<=48
            or not isinstance(venues,(list,tuple)) or not venues
            or len(set(venues))!=len(venues)
            or any(v not in VENUES for v in venues)):
        raise ValueError("invalid bounded multi-venue bridge search")
    proposals=missing_triangle_edge_targets(entries,maximum=360)
    # Pair novelty, not repeated hints: a verified new connection can
    # complete the triangle for an additional unique starting mint.
    pairs=[]
    seen=set()
    for target in proposals["targets"]:
        pair=tuple(sorted(target["pair"]))
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)
        if len(pairs)>=maximum_pairs:
            break
    if not pairs:
        return {"status":"NO_MISSING_BRIDGE_PAIRS","searched_pairs":[],
                "source_verified_new_pools":[],"verified_new_pool_count":0,
                "additional_candidate_start_mints":[],
                "source_search_venues":list(venues),
                "discovery_errors":[],"target_met_on_signed_simulations":False,
                **SAFE}
    if discovery_rpc is not None:
        if not isinstance(discovery_rpc,str) or not discovery_rpc.startswith("https://"):
            raise ValueError("separate discovery RPC must use HTTPS")
        if discover_fn is not None:
            raise ValueError("cannot combine alternate RPC with discovery injection")
        evidence=discover_on_separate_rpc(rpc,discovery_rpc,pairs,venues)
    else:
        discover_fn=discover_fn or discover
        evidence=discover_fn(rpc,pairs,limit=8,pace_seconds=0.5,
                             venues=list(venues))
    if (not isinstance(evidence,dict) or
            evidence.get("status") not in ("COMPLETE","PARTIAL",
                                            "UPSTREAM_RATE_LIMITED") or
            not isinstance(evidence.get("pools"),list)):
        raise ValueError("multi-venue source discovery failed evidence contract")
    allowed=set(pairs)
    existing={(row["venue"],row["address"]) for row in entries}
    selected={}
    for result in evidence["pools"]:
        if (not isinstance(result,dict) or
                result.get("venue") not in venues or
                not isinstance(result.get("address"),str) or
                not result["address"] or
                type(result.get("slot")) is not int or result["slot"]<0 or
                not isinstance(result.get("mints"),list) or
                len(result["mints"])!=2 or
                not all(isinstance(m,str) and m for m in result["mints"]) or
                result["mints"][0]==result["mints"][1] or
                tuple(sorted(result["mints"])) not in allowed or
                result.get("swap_simulated") is not False):
            raise ValueError("source pool not verified for requested bridge")
        identity=(result["venue"],result["address"])
        if identity in existing:
            continue
        candidate={"venue":result["venue"],"address":result["address"],
                   "mints":result["mints"],"source_verified_slot":result["slot"],
                   "source_verified_only":True}
        if identity in selected and selected[identity]["mints"]!=candidate["mints"]:
            raise ValueError("conflicting source pool identity")
        selected[identity]=candidate
    added=list(selected.values())
    before=topology(entries)
    after=topology(entries+added)
    return {"status":"READ_ONLY_MULTI_VENUE_BRIDGE_SCOUT",
            "discovery_status":evidence["status"],
            "discovery_rpc_mode":("SEPARATE_PROVIDER_SOURCE_REAUTHENTICATED"
                                  if discovery_rpc else "SOURCE_FORK"),
            "searched_venue_pairs":evidence.get("searched_venue_pairs"),
            "searched_pairs":[list(p) for p in pairs],
            "source_search_venues":list(venues),
            "source_verified_new_pools":added,
            "verified_new_pool_count":len(added),
            "before_three_hop_start_mints":before["three_hop_start_mint_count"],
            "after_source_verified_topology_start_mints":after["three_hop_start_mint_count"],
            "additional_candidate_start_mints":sorted(
                set(after["three_hop_start_mints"])-
                set(before["three_hop_start_mints"])),
            "discovery_errors":evidence.get("errors",[]),
            "target_met_on_signed_simulations":False,
            **SAFE}



def scout(rpc,entries,*,maximum=360,venues=DEFAULT_VENUES):
    suggestions=bridge_targets(entries,maximum=maximum)
    pairs=[tuple(x["pair"]) for x in suggestions["targets"]]
    if not pairs:raise ValueError("no topology bridge suggestions")
    if tuple(venues)!=("orca",):
        raise ValueError("direct PDA source scout supports Orca only")
    discovery=derive_orca_bridge_addresses(rpc,entries,suggestions["targets"])
    existing={(p["venue"],p["address"]) for p in entries}
    new=[{"venue":p["venue"],"address":p["address"],"mints":p["mints"],
          "source_verified_slot":p.get("slot"),"source_verified_only":True}
         for p in discovery["source_verified_pools"]
         if (p["venue"],p["address"]) not in existing]
    merged=entries+new
    before=suggestions["topology"]
    after=topology(merged)
    return {"status":"READ_ONLY_TOPOLOGY_BRIDGE_SCOUT",
            "registered_pool_count":len(entries),"source_verified_new_pool_count":len(new),
            "source_verified_new_pools":new,"before_three_hop_start_mints":before["three_hop_start_mint_count"],
            "after_source_verified_topology_start_mints":after["three_hop_start_mint_count"],
            "additional_candidate_start_mints":sorted(set(after["three_hop_start_mints"])-
                set(before["three_hop_start_mints"])),
            "minimum_target_start_mints":40,"target_met_on_source_topology":after["three_hop_start_mint_count"]>=40,
            "exploration_policy":"ALL_LEAF_TOKENS_BOTH_REMAINING_LIQUID_HUBS",
            "target_met_on_signed_simulations":False,
            "searched_bridge_pairs":pairs,"source_search_venues":["orca"],
            "derived_orca_pd_as_checked":discovery["candidate_pd_as_checked"],
            "source_whirlpool_config_count":discovery["source_whirlpool_config_count"],
            "candidate_tick_spacings":discovery["candidate_tick_spacings"],
            "discovery_status":"DIRECT_PDA_SOURCE_AUTHENTICATED",
            "discovery_errors":discovery["authentication_errors"],
            "suggested_registry_pool_count":len(merged),
            **SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--output",required=True)
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--maximum",type=int,default=360)
    p.add_argument("--venues",default="orca")
    a=p.parse_args()
    entries=json.loads(Path(a.registry).read_text())["pools"]
    result=scout(a.rpc,entries,maximum=a.maximum,venues=tuple(a.venues.split(",")))
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k not in
        ("source_verified_new_pools","discovery_errors","searched_bridge_pairs")}))
if __name__=="__main__":main()
