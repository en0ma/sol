"""Broaden all-seven candidate addresses using existing public discovery adapters.

Public hints NEVER establish pool authenticity. Local Surfpool snapshot verifies
owner, decoded mints, vaults, market and program before graph admission.
"""
import argparse,json
from pathlib import Path
from arb.next_ten_fork_pool_probe import PROGRAMS
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
BASE58=set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")

def merge(registry,feeds,*,limit_per_venue=12):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or not isinstance(feeds,dict) or set(feeds)!=set(PROGRAMS)
            or type(limit_per_venue)is not int or not 1<=limit_per_venue<=12):
        raise ValueError("invalid all-seven candidate discovery batch")
    seen={v:set() for v in PROGRAMS}
    result=[];counts={}
    for row in registry["pools"]:
        if not isinstance(row,dict):raise ValueError("malformed source registry")
        v=row.get("venue");a=row.get("address")
        if v not in PROGRAMS:continue
        if not isinstance(a,str) or not 32<=len(a)<=44 or any(x not in BASE58 for x in a):
            raise ValueError("invalid pinned pool")
        if a in seen[v] or len(seen[v])>=limit_per_venue:continue
        seen[v].add(a);result.append(dict(row))
    for venue in PROGRAMS:
        feed=feeds[venue]
        if not isinstance(feed,list) or len(feed)>1000:
            raise ValueError("unbounded public hint feed")
        offered=0;appended=0
        for hint in feed:
            a=hint.get("address") if isinstance(hint,dict) else hint
            if not isinstance(a,str) or not 32<=len(a)<=44 or any(c not in BASE58 for c in a):
                continue
            offered+=1
            if a in seen[venue] or len(seen[venue])>=limit_per_venue:continue
            seen[venue].add(a);appended+=1
            result.append({"venue":venue,"address":a,"source":"UNTRUSTED_PUBLIC_HINT",
                           "onchain_authenticated":False,**SAFE})
        counts[venue]={"offered":offered,"appended":appended,
                       "total_candidates":len(seen[venue])}
    return {"pools":result,"discovery":{"status":"UNTRUSTED_HINTS_REQUIRE_SOURCE_RPC",
        "coverage":counts,"total_candidates":len(result),**SAFE}}

def choose_connectivity_leads(leads,registry,limit):
    """Greedily prefer new token links joining already observed token paths.

    Uses UNTRUSTED advertised mints only to prioritize local-RPC probes, never
    to approve a route, quote, or pool. Existing registry mint edges are hints.
    """
    from collections import defaultdict
    if type(limit)is not int or not 1<=limit<=12:
        raise ValueError("invalid connectivity bound")
    edges=set()
    for pool in registry.get("pools",[]):
        m=pool.get("mints")
        if isinstance(m,list) and len(m)==2 and all(isinstance(x,str) for x in m) and m[0]!=m[1]:
            edges.add(frozenset(m))
    pending=[];seen=set()
    for lead in leads:
        if not isinstance(lead,dict):continue
        address=lead.get("address");m=lead.get("mints")
        if (not isinstance(address,str) or address in seen or
                not isinstance(m,list) or len(m)!=2 or m[0]==m[1] or
                any(not isinstance(x,str) for x in m)):
            continue
        pending.append(lead);seen.add(address)
    chosen=[]
    while pending and len(chosen)<limit:
        neighbor=defaultdict(set)
        for edge in edges:
            a,b=tuple(edge);neighbor[a].add(b);neighbor[b].add(a)
        active=set(neighbor)
        def score(lead):
            a,b=lead["mints"];edge=frozenset((a,b))
            # A new edge joining two already connected vertices can create
            # a longer mint-simple route. Avoid exhausting slots on leaves.
            return (int(a in active and b in active and edge not in edges),
                    int(a in active)+int(b in active),
                    int(edge not in edges),
                    int(lead.get("matching_peer_mints") is True))
        winner=max(range(len(pending)),key=lambda i:score(pending[i]))
        lead=pending.pop(winner);chosen.append(lead["address"])
        edges.add(frozenset(lead["mints"]))
    return chosen

def collect(*,limit_per_venue=12,registry=None):
    feeds={v:[] for v in PROGRAMS}
    errors={}
    def attempt(venue,fn):
        try:feeds[venue]=fn()
        except (ValueError,KeyError,TypeError,OSError,TimeoutError,RuntimeError) as exc:
            errors[venue]=type(exc).__name__+": "+str(exc)[:180]
    from arb.orca_api_discovery import fetch_page,parse_page
    attempt("orca",lambda:parse_page(fetch_page(size=50))[0])
    from arb.atomic_missing_venue_candidates import (
        discover_amm_v4_candidates,discover_clmm_candidates)
    # Feed the existing peer inventory to the Raydium public discovery adapters.
    # Global public enumeration is bounded and does not assume a fixed token pair.
    attempt("raydium_amm_v4",lambda:choose_connectivity_leads(
            discover_amm_v4_candidates(registry or {"pools":[]},max_pages=2),
            registry or {"pools":[]},limit_per_venue))
    attempt("raydium_clmm",lambda:choose_connectivity_leads(
            discover_clmm_candidates(registry or {"pools":[]},max_pages=2),
            registry or {"pools":[]},limit_per_venue))
    from arb.indexed_pool_discovery import fetch_candidates
    for v in ("meteora_dlmm","meteora_damm_v2"):
        attempt(v,lambda venue=v:fetch_candidates(venue,page_size=100))
    # PumpSwap is mint-scoped; derive a dynamic list from authenticated
    # registry mints in collect_for_registry instead of assuming WSOL-only.
    return feeds,errors

def collect_for_registry(registry,*,limit_per_venue=12):
    feeds,errors=collect(limit_per_venue=limit_per_venue,registry=registry)
    from arb.pumpswap_indexed_discovery import fetch
    from arb.onchain_pool_discovery import MINTS
    mints=list(dict.fromkeys(m for p in registry["pools"] if isinstance(p,dict)
                             for m in p.get("mints",[]) if isinstance(m,str)))
    mints=list(dict.fromkeys(mints+list(MINTS.values())))[:8]
    for mint in mints:
        if len(feeds["pumpswap"])>=limit_per_venue:break
        try:feeds["pumpswap"].extend(fetch(mint,page=1))
        except (ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
            errors["pumpswap:"+mint[:8]]=type(exc).__name__+": "+str(exc)[:180]
    # CPMM source pool identities currently require pinned registry or on-chain
    # filtered discovery. Do not pretend AMM v4 index is CPMM.
    errors["raydium_cpmm"]="PUBLIC_WIDE_POOL_FEED_NOT_CONNECTED_PINNED_AND_ONCHAIN_ONLY"
    return feeds,errors

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--max-per-venue",type=int,default=12)
    a=p.parse_args()
    registry=json.loads(Path(a.registry).read_text())
    feeds,errors=collect_for_registry(registry,limit_per_venue=a.max_per_venue)
    report=merge(registry,feeds,limit_per_venue=a.max_per_venue)
    report["discovery"]["source_errors"]=errors
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report["discovery"]))
if __name__=="__main__":main()
