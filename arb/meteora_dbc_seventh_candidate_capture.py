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


def run(rpc, *, count=1, hint_limit=24, pages=4, strict=True, candidate_validator=None):
    if type(count) is not int or not 1 <= count <= 6:
        raise ValueError("DBC accepted source count must be 1-6")
    if type(hint_limit) is not int or not count <= hint_limit <= 24:
        raise ValueError("DBC bounded hint limit required")
    source = "original_dbc_program_recent_transactions"
    try:
        hinted=onchain_discover(rpc,count=hint_limit,max_signatures=64,pages=pages)
        print(json.dumps({"stage":"dbc_program_transactions",
            "hinted":len(hinted["hints"]),
            "transactions":hinted["program_transactions_checked"]}))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"stage":"dbc_program_transactions",
            "error_type":type(exc).__name__}))
        hinted={"hints":[]}
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
            if candidate_validator is not None:
                candidate_validator(state)
            accepted.append(state)
        except (ValueError, OSError, RuntimeError, KeyError, TypeError) as exc:
            reason={"address":address,"reason_type":type(exc).__name__}
            if isinstance(exc, ValueError):
                reason["validation_reason"]=str(exc)[:160]
            rejected.append(reason)
            print(json.dumps({"stage":"dbc_candidate_rejected",**reason}))
        if len(accepted)>=count:
            break
    # Exhaust original transaction hints before consulting an untrusted index.
    # This prevents network-dependent regression tests and unnecessary HTTP
    # calls when authentic on-chain hints already satisfy the target.
    if len(accepted)<count:
        try:
            public=public_discover(count=min(6,hint_limit))
            seen={entry["address"] for entry in hinted["hints"]}
            for entry in public["hints"]:
                address=entry["address"]
                if address in seen:
                    continue
                seen.add(address)
                try:
                    result=capture(rpc,count=1,pool_addresses=[address])
                    if result["authenticated"]!=1:
                        raise ValueError("DBC original pool identity not authenticated")
                    state=capture_pool(rpc,result["source_pools"][0])
                    if candidate_validator is not None:
                        candidate_validator(state)
                    accepted.append(state)
                except (ValueError,OSError,RuntimeError,KeyError,TypeError) as exc:
                    reason={"address":address,"reason_type":type(exc).__name__}
                    if isinstance(exc,ValueError):
                        reason["validation_reason"]=str(exc)[:160]
                    rejected.append(reason)
                    print(json.dumps({"stage":"dbc_candidate_rejected",**reason}))
                if len(accepted)>=count:
                    break
        except (OSError,RuntimeError,ValueError,KeyError,TypeError) as exc:
            print(json.dumps({"stage":"dbc_public_index_unavailable",
                "error_type":type(exc).__name__}))
    if len(accepted)!=count and strict:
        raise ValueError("DBC original contextual source target incomplete: "+
                         str(len(accepted))+" of "+str(count))
    return {"venue":"meteora_dbc",
       "status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED",
       "source_pools":accepted,"authenticated":len(accepted),
       "source_target":count,"source_target_met":len(accepted)==count,
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
    ap.add_argument("--hint-limit",type=int,default=24)
    ap.add_argument("--pages",type=int,default=4)
    ap.add_argument("--sdk-screen",action="store_true")
    ap.add_argument("--output",required=True)
    a=ap.parse_args()
    validator=None
    if a.sdk_screen:
        from arb.meteora_dbc_six_source_qualification import validate_official_sdk_candidate
        validator=validate_official_sdk_candidate
    report=run(a.rpc,count=a.count,hint_limit=a.hint_limit,pages=a.pages,
               candidate_validator=validator)
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated":report["authenticated"],
                      "rejected_candidate_count":report["rejected_candidate_count"],
                      "signed_verified_pools":0}))


if __name__=="__main__":
    main()
