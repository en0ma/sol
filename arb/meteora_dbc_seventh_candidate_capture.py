"""Real DBC bounded source candidate pipeline, fail closed on partial evidence.

Public discovery never establishes any signed, price or registry acceptance.
All original account bytes must be authenticated by owner and synchronized.
"""
import argparse
import json
from pathlib import Path
from arb.meteora_dbc_seventh_discovery import discover
from arb.meteora_dbc_seventh_venue_source import capture
from arb.meteora_dbc_seventh_state_capture import capture_pool


def run(rpc, *, count=1):
    hints=discover(count=count)
    if len(hints["hints"])<count:
        raise ValueError("DBC insufficient untrusted public hints")
    identities=capture(rpc,count=count,pool_addresses=[
        x["address"] for x in hints["hints"]
    ])
    if identities["authenticated"]!=count:
        raise ValueError("DBC candidate source authentication incomplete")
    states=[capture_pool(rpc,p) for p in identities["source_pools"]]
    return {"venue":"meteora_dbc",
       "status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED",
       "source_pools":states,"authenticated":len(states),
       "source_eligible_not_pricing_verified":len(states),
       "native_pricing_verified":False,
       "official_sdk_parity_verified":False,
       "signed_parity_verified":False,
       "registry_admission_approved":False,
       "actionable":False,"broadcast":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc",required=True)
    ap.add_argument("--count",type=int,default=1)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    report=run(a.rpc,count=a.count)
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated":report["authenticated"],
                      "signed_verified_pools":0}))


if __name__=="__main__":
    main()
