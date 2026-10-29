"""Bounded six original Meteora DBC pool source qualification.

Only original account bytes + independent source audits; six successful pool
identities do NOT imply six SDK/native quote parities or 24 signed swaps.
"""
import argparse,json
from pathlib import Path
from arb.meteora_dbc_seventh_candidate_capture import run
from arb.meteora_dbc_seventh_source_audit import independently_audit


def qualify(rpc, *, count=6, hint_limit=24, pages=4):
    if type(count) is not int or count!=6:
        raise ValueError("DBC seventh venue six distinct source pools required")
    captured=run(rpc,count=count,hint_limit=hint_limit,pages=pages,strict=False)
    addresses=[p["pool"] for p in captured["source_pools"]]
    if len(addresses)!=6 or len(set(addresses))!=6:
        raise ValueError("DBC six unique pool identities not established")
    audit=independently_audit(captured)
    if audit["authenticated_source_pools"]!=6:
        raise ValueError("DBC six independent original source audits incomplete")
    return {"venue":"meteora_dbc","status":"SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY",
        "source":captured,"independent_audit":audit,
        "authenticated_source_pools":6,"native_pricing_verified":False,
        "official_sdk_parity_verified":False,"signed_swaps_verified":0,
        "signed_parity_verified":False,"registry_admission_approved":False,
        "actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--pages",type=int,default=6)
    a=p.parse_args()
    captured=run(a.rpc,count=6,hint_limit=24,pages=a.pages,strict=False)
    count=len(captured["source_pools"])
    audit=(independently_audit(captured) if count else
           {"authenticated_source_pools":0,"pools":[],
            "signed_parity_verified":False})
    if audit["authenticated_source_pools"]!=count:
        raise SystemExit("DBC original source audit count mismatch")
    complete=(count==6 and len({p["pool"] for p in captured["source_pools"]})==6)
    result={"venue":"meteora_dbc",
       "status":"SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY" if complete else
                "PARTIAL_DBC_ORIGINAL_SOURCE_EVIDENCE_NOT_ACCEPTED",
       "source":captured,"independent_audit":audit,
       "authenticated_source_pools":count,"target_source_pools":6,
       "native_pricing_verified":False,"signed_swaps_verified":0,
       "signed_parity_verified":False,"registry_admission_approved":False,
       "actionable":False,"broadcast":False}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\\n")
    print(json.dumps({"status":result["status"],
       "authenticated_source_pools":count,"target":6,
       "signed_swaps_verified":0}))
    if not complete:
        raise SystemExit("DBC six independently authenticated pools not reached")


if __name__=="__main__":main()
