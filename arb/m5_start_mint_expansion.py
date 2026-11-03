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
        connected_hubs=sorted(set(neighbors)&set(HUBS))
        if not connected_hubs:
            continue
        for target in HUBS:
            if target in neighbors or tuple(sorted((mint,target))) in current_pairs:
                continue
            old=next((hub for hub in connected_hubs
                      if tuple(sorted((hub,target))) in current_pairs),None)
            if old is None:
                continue
            candidates.append({"mint":mint,"connected_hub":old,"missing_hub":target,
                               "pair":[mint,target],"current_pools":count[mint]})
    # Prefer established tokens with multiple authenticated pool identity hints.
    # Keep both missing-hub options adjacent; avoid 36 requests for one mint.
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
    chosen={}
    counts=defaultdict(int)
    covered=set()
    while len(covered)<target_start_mints:
        best=None
        best_score=None
        for tokens,edges in triples:
            new_mints=sum(t not in covered for t in tokens)
            if not new_mints:continue
            # Prefer reuse of already scheduled identities, with a bounded
            # six-option search per pair to avoid dense hub combinatorics.
            options=[sorted(poolset,key=lambda p:(
                p["address"] not in chosen,counts[p["venue"]],
                p["venue"],p["address"]))[:6] for poolset in edges]
            for candidate in product(*options):
                identities={(p["venue"],p["address"]) for p in candidate}
                if len(identities)!=3:continue
                additions=[p for p in candidate if (p["venue"],p["address"]) not in chosen]
                increments=defaultdict(int)
                for row in additions:increments[row["venue"]]+=1
                if any(counts[v]+inc>maximum_per_venue for v,inc in increments.items()):
                    continue
                # New start mints take precedence over pool density.
                score=(new_mints,-len(additions),
                       -sum(counts[p["venue"]] for p in candidate),
                       tuple(tokens))
                if best_score is None or score[:3]>best_score[:3]:
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
            "source_authenticated":False,
            "signed_simulation_verified":False,
            **SAFE}

def derive_orca_bridge_addresses(rpc,entries,targets,*,spacings=(1,2,4,8,16,32,64,128)):
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
            "source_whirlpool_config_count":len(configs),"authentication_errors":errors}

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
