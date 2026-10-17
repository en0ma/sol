"""Bounded multi-batch direct-RPC registry validation.

Each batch uses the existing strict pool_registry.refresh; no indexer evidence
is promoted, and cross-batch duplicate identities are explicitly rejected.
"""
from arb.onchain_pool_discovery import VENUES
from arb.pool_registry import refresh

def refresh_batched(rpc, entries, batch_size=100, max_entries=2000):
    if (not isinstance(entries,list) or type(batch_size) is not int or
            not 1 <= batch_size <= 200 or type(max_entries) is not int or
            not 1 <= max_entries <= 2000 or len(entries)>max_entries):
        raise ValueError("invalid bounded registry batch")
    seen=set()
    unique=[]
    duplicates=[]
    for entry in entries:
        if isinstance(entry,dict) and isinstance(entry.get("venue"),str) and isinstance(entry.get("address"),str):
            key=(entry["venue"],entry["address"])
            if key in seen:
                duplicates.append({"venue":key[0],"address":key[1],"reason":"DUPLICATE"})
                continue
            seen.add(key)
        unique.append(entry)
    valid=[]
    rejected=list(duplicates)
    for index in range(0,len(unique),batch_size):
        result=refresh(rpc,unique[index:index+batch_size])
        valid.extend(result["verified_pools"])
        rejected.extend(result["rejected"])
    pairs={}
    for pool in valid:
        key=tuple(sorted(pool["mints"]))
        pairs.setdefault(key,[]).append({"venue":pool["venue"],"address":pool["address"]})
    shared=[{"mints":list(pair),"pools":pools} for pair,pools in pairs.items()
            if len({p["venue"] for p in pools})>1]
    coverage={name:{"validated_pools":sum(p["venue"]==name for p in valid),
                    "rejected_pools":sum(p.get("venue")==name for p in rejected)}
              for name in VENUES}
    return {"status":"COMPLETE" if not rejected else "PARTIAL",
            "candidate_count":len(entries), "batch_count":(len(unique)+batch_size-1)//batch_size,
            "verified_count":len(valid),"rejected_count":len(rejected),
            "verified_pools":valid,"rejected":rejected,
            "shared_pairs":shared,"venue_validation_coverage":coverage,
            "opportunities_executed":0,"broadcast":False}
