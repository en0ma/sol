"""Bounded authenticated pool snapshots for simulation-only market research.

No API-provided 'verified' bit can authenticate an account by itself: ingest
only records accompanied by a trusted fork verifier's explicit attestation.
Immutable snapshot batches prevent silent mixing of slots or stale observations.
"""
from arb.execution_target_matrix import TARGET_VENUES
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}
MAX_POOLS=2000

def normalize(records,*,as_of_unix,max_age_seconds=60,max_slot_skew=32):
    if type(as_of_unix)is not int or as_of_unix<0 or type(max_age_seconds)is not int or max_age_seconds<1 or type(max_slot_skew)is not int or max_slot_skew<0:
        raise ValueError("invalid time/slot bounds")
    if not isinstance(records,list) or len(records)>MAX_POOLS:
        raise ValueError("invalid pool registry batch")
    eligible=[];rejections=[];seen=set()
    for i,item in enumerate(records):
        errors=[]
        if not isinstance(item,dict):
            rejections.append({"index":i,"reasons":["malformed record"]})
            continue
        key=(item.get("venue"),item.get("address"))
        if key in seen:errors.append("duplicate venue/pool")
        seen.add(key)
        if item.get("venue") not in TARGET_VENUES:errors.append("unsupported venue")
        if not isinstance(item.get("address"),str) or not item["address"]:errors.append("invalid pool address")
        mints=item.get("mints")
        if not isinstance(mints,(list,tuple)) or len(mints)!=2 or not all(isinstance(v,str) and v for v in mints) or mints[0]==mints[1]:
            errors.append("invalid mint pair")
        observed=item.get("observed_unix")
        if type(observed)is not int or observed<0 or observed>as_of_unix or as_of_unix-observed>max_age_seconds:
            errors.append("stale/future state")
        slot=item.get("slot")
        if type(slot)is not int or slot<0:errors.append("invalid slot")
        if item.get("source_authenticated") is not True or item.get("verified") is not True or item.get("account_owner_verified") is not True:
            errors.append("independent chain account authentication missing")
        if item.get("snapshot_origin")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
            errors.append("unsupported snapshot origin")
        if errors:rejections.append({"index":i,"reasons":errors})
        else:eligible.append(dict(item))
    ceiling=max((x["slot"] for x in eligible),default=None)
    valid=[]
    for item in eligible:
        if ceiling-item["slot"]>max_slot_skew:
            rejections.append({"venue":item["venue"],"address":item["address"],"reasons":["cross-pool slot skew"]})
        else:valid.append(item)
    return {"status":"AUTHENTICATED_REGISTRY_SNAPSHOT","as_of_unix":as_of_unix,
            "pool_count":len(valid),"pools":valid,"rejections":rejections,
            "max_slot":ceiling,"source_rpc_calls":0,**SAFETY}
