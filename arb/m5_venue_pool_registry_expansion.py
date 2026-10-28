"""Extend existing venue-owned pool registries; do not create swap/pricing runners.

Orca and Meteora discovery provide UNTRUSTED addresses. The existing
on-chain registry validator uses each venue's own decoder and vault checks.
No source address becomes a registered pool without successful authentication.
"""
import argparse,json
from pathlib import Path
from arb.pool_registry_batches import refresh_batched
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def discover_new(rpc,registry,venue,*,count=6,pages=4):
    if venue not in ("orca","meteora_damm_v2") or type(count)is not int or not 1<=count<=20:
        raise ValueError("unsupported venue/count")
    existing={r["address"] for r in registry["pools"] if r.get("venue")==venue}
    candidates=[]
    if venue=="orca":
        from arb.orca_api_discovery import fetch_page,parse_page
        cursor=None;seen_cursors=set()
        for _ in range(pages):
            entries,next_cursor=parse_page(fetch_page(cursor=cursor,size=100,min_tvl=0))
            candidates.extend(entries)
            if not next_cursor:break
            if next_cursor in seen_cursors:raise ValueError("Orca cursor cycle")
            seen_cursors.add(next_cursor);cursor=next_cursor
    else:
        from arb.indexed_pool_discovery import fetch_candidates
        for page in range(1,pages+1):
            candidates.extend(fetch_candidates(venue,page=page,page_size=100))
    unseen=[];seen=set()
    for row in candidates:
        a=row.get("address") if isinstance(row,dict) else None
        if not isinstance(a,str) or not a or a in existing or a in seen:continue
        seen.add(a)
        unseen.append({"venue":venue,"address":a})
    # Existing decoder/owner/mint/vault checks; untrusted API output never
    # becomes a registry entry until the source RPC proves it.
    verified=[]
    rejected=[]
    for offset in range(0,len(unseen),100):
        if len(verified)>=count:break
        result=refresh_batched(rpc,unseen[offset:offset+100],batch_size=100)
        verified.extend(result["verified_pools"])
        rejected.extend(result["rejected"])
    accepted=verified[:count]
    if len({p["address"] for p in accepted})!=len(accepted):
        raise ValueError("duplicate validated venue pool")
    identities=[{"venue":venue,"address":p["address"],"mints":p["mints"]}
                for p in accepted]
    return {"venue":venue,"already_registered_count":len(existing),
            "unseen_candidate_count":len(unseen),
            "new_authenticated_count":len(identities),
            "required_new_count":count,"new_authenticated_pools":identities,
            "rejections":rejected[:100],
            "status":"VENUE_REGISTRY_EXPANSION_READY" if len(identities)==count
                     else "VENUE_REGISTRY_EXPANSION_INCOMPLETE",**SAFE}

def expand(rpc,registry,*,count=6,pages=4):
    reports=[discover_new(rpc,registry,v,count=count,pages=pages)
             for v in ("orca","meteora_damm_v2")]
    accepted=[p for report in reports for p in report["new_authenticated_pools"]]
    registered={(p["venue"],p["address"]) for p in registry["pools"]}
    for row in accepted:
        key=(row["venue"],row["address"])
        if key in registered:raise ValueError("venue registry duplicate promotion")
        registered.add(key)
    next_registry={**registry,"pools":[*registry["pools"],*accepted]}
    complete=all(r["new_authenticated_count"]==count for r in reports)
    return next_registry,{"status":"BOTH_VENUES_SIX_NEW_POOLS_AUTHENTICATED"
                             if complete else "POOL_DISCOVERY_INCOMPLETE",
        "venues":reports,"registered_additional_pools":len(accepted),
        "native_pricing_signed_verified":False,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--count",type=int,default=6)
    p.add_argument("--pages",type=int,default=4)
    p.add_argument("--output-registry",required=True)
    p.add_argument("--report",required=True)
    a=p.parse_args()
    registry=json.loads(Path(a.registry).read_text())
    expanded,report=expand(a.rpc,registry,count=a.count,pages=a.pages)
    Path(a.output_registry).write_text(json.dumps(expanded,indent=2)+"\n")
    Path(a.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "registered_additional_pools":report["registered_additional_pools"],**SAFE}))
    if report["status"]!="BOTH_VENUES_SIX_NEW_POOLS_AUTHENTICATED":
        raise SystemExit("six NEW authenticated pools per venue not yet discovered")

if __name__=="__main__":main()
