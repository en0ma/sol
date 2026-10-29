"""Bounded fail-closed DBC public-hint to original source capture.

Meteora DBC active pools are often short lived and many use Token-2022.
Untrusted index candidates are tried independently; none can bypass the
program ELF, source hash, PoolConfig, vault or migration checks.
"""
import argparse
import json
from pathlib import Path
from arb.meteora_dbc_seventh_discovery import discover as public_discover
from arb.meteora_dbc_seventh_recent_tx_discovery import discover as onchain_discover
from arb.meteora_dbc_seventh_venue_source import capture
from arb.meteora_dbc_seventh_state_capture import capture_pool


def run(rpc, *, count=1, hint_limit=6):
    if type(count) is not int or not 1 <= count <= 6:
        raise ValueError("DBC accepted source count must be 1-6")
    if type(hint_limit) is not int or not count <= hint_limit <= 6:
        raise ValueError("DBC bounded hint limit required")
    source = "original_dbc_program_recent_transactions"
    try:
        hinted=onchain_discover(rpc,count=hint_limit,max_signatures=16)
        print(json.dumps({"stage":"dbc_program_transactions",
            "hinted":len(hinted["hints"]),
            "transactions":hinted["program_transactions_checked"]}))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"stage":"dbc_program_transactions",
            "error_type":type(exc).__name__}))
        hinted={"hints":[]}
    if not hinted["hints"]:
        # Still untrusted and independently authenticated in the next stages.
        source="dexpaprika_untrusted_fallback"
        hinted=public_discover(count=hint_limit)
        print(json.dumps({"stage":"dbc_public_index",
            "hinted":len(hinted["hints"])}))
    if not hinted["hints"]:
        raise ValueError("DBC no candidate identities from original transactions or public index")
    accepted=[]
    rejected=[]
    for entry in hinted["hints"]:
        address=entry["address"]
        try:
            # Reauthenticate against original on-chain owner, original executable
            # program, and exact live account bytes; index never conveys state.
            result=capture(rpc,count=1,pool_addresses=[address])
            if result["authenticated"]!=1:
                raise ValueError("DBC original pool identity not authenticated")
            state=capture_pool(rpc,result["source_pools"][0])
            accepted.append(state)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            rejected.append({"address":address,
                             "reason_type":type(exc).__name__})
        if len(accepted)>=count:
            break
    if len(accepted)!=count:
        raise ValueError("DBC original contextual source target incomplete: "+
                         str(len(accepted))+" of "+str(count))
    return {"venue":"meteora_dbc",
       "status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED",
       "source_pools":accepted,"authenticated":len(accepted),
       "discovery_source":source,
       "rejected_candidate_count":len(rejected),
       "rejected_candidates":rejected,
       "source_eligible_not_pricing_verified":len(accepted),
       "native_pricing_verified":False,
       "official_sdk_parity_verified":False,
       "signed_parity_verified":False,
       "registry_admission_approved":False,
       "actionable":False,"broadcast":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rpc",required=True)
    ap.add_argument("--count",type=int,default=1)
    ap.add_argument("--hint-limit",type=int,default=6)
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    report=run(a.rpc,count=a.count,hint_limit=a.hint_limit)
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated":report["authenticated"],
                      "rejected_candidate_count":report["rejected_candidate_count"],
                      "signed_verified_pools":0}))


if __name__=="__main__":
    main()
