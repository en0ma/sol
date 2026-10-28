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
        rejected.extend(result["rejected"])
        for pool in result["verified_pools"]:
            if venue=="meteora_damm_v2":
                # Existing venue-specific source fee decoder must accept the
                # actual on-chain bytes before pool admission for native quote.
                import base64
                from arb.rpc import call
                from arb.meteora_damm_v2_source_fee_decoder import decode_fee_state
                try:
                    info=call(rpc,"getAccountInfo",[pool["address"],
                         {"encoding":"base64","commitment":"confirmed"}])["value"]
                    if not isinstance(info,dict):
                        raise ValueError("source DAMM account missing")
                    decode_fee_state(base64.b64decode(info["data"][0],validate=True))
                except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                    rejected.append({"venue":venue,"address":pool["address"],
                        "reason":"VENUE_FEE_DECODER_UNSUPPORTED: "+str(exc)[:150]})
                    continue
            verified.append(pool)
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
    # These are verified identities, NOT execution-eligible registry entries.
    # Only signed price parity promotes an address into the usable registry.
    complete=all(r["new_authenticated_count"]==count for r in reports)
    return registry,{"status":"BOTH_VENUES_SIX_NEW_POOLS_AUTHENTICATED"
                             if complete else "POOL_DISCOVERY_INCOMPLETE",
        "venues":reports,"authenticated_candidate_count":len(accepted),
        "registered_additional_pools":0,
        "native_pricing_signed_verified":False,**SAFE}

def promote_signed(registry,candidates,orca_receipt,meteora_receipt,*,required=6):
    """Only complete 4/4 signed SDK/native execution parity enters registry."""
    specifications=(
        ("orca",orca_receipt,"ORCA_NEW_POOLS_SIGNED_VERIFIED"),
        ("meteora_damm_v2",meteora_receipt,"METEORA_DAMM_V2_CONFIGURED_POOLS_SIGNED_VERIFIED"))
    allowed={}
    for venue,receipt,status in specifications:
        if receipt.get("status")!=status or not isinstance(receipt.get("pools"),list):
            raise ValueError(venue+" signed verification did not succeed")
        validated=[]
        for pool in receipt["pools"]:
            if (pool.get("verified") is True and
                    (pool.get("exact",pool.get("exact_matches"))==4) and
                    (pool.get("trial_count",len(pool.get("trials",[])))==4) and
                    len(pool.get("trials",[]))==4):
                validated.append(pool.get("pool"))
        if len(set(validated))<required:
            raise ValueError(venue+" fewer than six distinct 4/4 signed pools")
        allowed[venue]=set(validated)
    existing={(row["venue"],row["address"]) for row in registry["pools"]}
    fresh=[]
    for row in candidates["pools"]:
        venue,address=row.get("venue"),row.get("address")
        if venue in allowed and address in allowed[venue] and (venue,address) not in existing:
            fresh.append(row)
            existing.add((venue,address))
    if any(sum(row["venue"]==venue for row in fresh)<required for venue in allowed):
        raise ValueError("signed pool identity not in authenticated discovery candidate list")
    return {**registry,"pools":[*registry["pools"],*fresh]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--count",type=int,default=6)
    p.add_argument("--pages",type=int,default=4)
    p.add_argument("--output-registry",required=True)
    p.add_argument("--output-new-pools",required=True)
    p.add_argument("--report",required=True)
    a=p.parse_args()
    registry=json.loads(Path(a.registry).read_text())
    expanded,report=expand(a.rpc,registry,count=a.count,pages=a.pages)
    Path(a.output_registry).write_text(json.dumps(expanded,indent=2)+"\n")
    additions=[p for venue in report["venues"] for p in venue["new_authenticated_pools"]]
    Path(a.output_new_pools).write_text(json.dumps({"pools":additions},indent=2)+"\n")
    Path(a.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated_candidate_count":report["authenticated_candidate_count"],
                      "registered_additional_pools":0,**SAFE}))
    if report["status"]!="BOTH_VENUES_SIX_NEW_POOLS_AUTHENTICATED":
        raise SystemExit("six NEW authenticated pools per venue not yet discovered")

if __name__=="__main__":main()
