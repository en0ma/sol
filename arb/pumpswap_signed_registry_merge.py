"""Persist *only* independently audited PumpSwap signed pool proofs into existing registry.

No new discovery or coordinator. This is an offline evidence-only registry merge;
it cannot produce a verified pool without a real signed report passing the
full cryptographic, native SDK and raw SPL account auditors.
"""
import argparse
import hashlib
import json
from pathlib import Path
from arb.pumpswap_signed_receipt_audit import audit


def merge(registry,source,sdk,signed,*,required_additional=6):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or type(required_additional) is not int or required_additional<1):
        raise ValueError("existing registry and new signed target required")
    independent=audit(source,sdk,signed)
    accepted=independent["pools"]
    source_index={r["address"]:r for r in source["pools"]}
    rows=list(registry["pools"])
    indexed={(r["venue"],r["address"]):i for i,r in enumerate(rows)}
    if len(indexed)!=len(rows):
        raise ValueError("duplicate existing registry identity")
    added=0
    updated=0
    for record in accepted:
        address=record["pool"]
        observed=source_index[address]
        signed_provenance={
            "status":"INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
            "source_slot":record["source_slot"],
            "source_digest":record["source_digest"],
            "signed_transaction_hashes":record["signed_transaction_hashes"],
            "independent_receipt_sha256":hashlib.sha256(json.dumps(
                record,sort_keys=True,separators=(",",":")).encode()).hexdigest(),
        }
        key=("pumpswap",address)
        if key in indexed:
            previous=rows[indexed[key]]
            if previous.get("mints")!=observed["mints"]:
                raise ValueError("registered PumpSwap mint identity changed")
            prior=previous.get("signed_provenance")
            if prior is not None and prior!=signed_provenance:
                # A new independent run changes the slot/transaction signatures,
                # but must not overwrite immutable earlier provenance.
                history=previous.get("signed_provenance_history",[])
                if not isinstance(history,list) or any(not isinstance(p,dict) for p in history):
                    raise ValueError("invalid signed provenance history")
                known={p.get("independent_receipt_sha256") for p in history}
                if signed_provenance["independent_receipt_sha256"] not in known:
                    rows[indexed[key]]={**previous,
                        "signed_provenance_history":[*history,signed_provenance]}
                    updated+=1
            elif prior is None:
                rows[indexed[key]]={**previous,"signed_provenance":signed_provenance}
                added+=1
        else:
            rows.append({"venue":"pumpswap","address":address,
                         "mints":observed["mints"],"signed_provenance":signed_provenance})
            indexed[key]=len(rows)-1
            added+=1
    # Previously unverified registry hints count as new signed admissions;
    # the already signed seed pool does not count as a new pool.
    if added<required_additional:
        raise ValueError("fewer than requested NEW PumpSwap signed-verified pools: "+
                         str(added)+"/"+str(required_additional))
    result={**registry,"pools":rows}
    verified=sum(r.get("venue")=="pumpswap" and isinstance(r.get("signed_provenance"),dict)
                 for r in result["pools"])
    return result,{"venue":"pumpswap","new_signed_verified_pools":added,
                   "total_signed_verified_pools":verified,
                   "previously_signed_recaptures":updated,
                   "required_additional":required_additional,
                   "status":"PUMPSWAP_SIX_ADDITIONAL_SIGNED_VERIFIED",
                   "actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("registry","source","sdk","signed","output","report"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--additional",type=int,default=6)
    args=p.parse_args()
    result,receipt=merge(json.loads(Path(args.registry).read_text()),
                         json.loads(Path(args.source).read_text()),
                         json.loads(Path(args.sdk).read_text()),
                         json.loads(Path(args.signed).read_text()),
                         required_additional=args.additional)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    Path(args.report).write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))


if __name__=="__main__":
    main()
