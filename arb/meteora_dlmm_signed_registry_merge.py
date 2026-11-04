"""Fifth venue: signed DLMM pools into the existing registry, fail-closed.

Evidence must independently reconstruct four REAL signed transaction intents
and SPL deltas, and both SDK plus native integer quote against authenticated
same-slot source. No new registry, coordinator or execution permission.
"""
import argparse,hashlib,json
from pathlib import Path
from arb.meteora_dlmm_fifth_signed_audit import audit

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False,
      "registry_admission_approved":False}


def merge(registry,source,sdk,signed,*,required_verified=1):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or type(required_verified) is not int or not 1<=required_verified<=6):
        raise ValueError("existing pool registry and bounded DLMM count required")
    verified=audit(source,sdk,signed)
    if verified["independently_signed_verified_pools"]<required_verified:
        raise ValueError("DLMM fewer than required independently signed pools")
    indexed={(row.get("venue"),row.get("address")):i
             for i,row in enumerate(registry["pools"])}
    if len(indexed)!=len(registry["pools"]):
        raise ValueError("existing venue registry contains duplicate identities")
    source_index={p.get("address"):p for p in source.get("pools",[])}
    rows=[dict(item) for item in registry["pools"]]
    accepted=0
    for proof in verified["pools"]:
        address=proof["pool"]
        source_row=source_index.get(address)
        key=("meteora_dlmm",address)
        if key not in indexed or not isinstance(source_row,dict):
            raise ValueError("DLMM signed pool absent from pre-tracked authenticated registry")
        registry_row=rows[indexed[key]]
        if registry_row.get("mints")!=source_row["mints"]:
            raise ValueError("DLMM source mints disagree with registered pool")
        if (proof["source_sha256"]!=source_row["source_sha256"] or
                proof["source_slot"]!=source_row["source_slot"]):
            raise ValueError("DLMM independent signed source provenance mismatch")
        hashes=proof["signed_transaction_hashes"]
        if (len(hashes)!=4 or len(set(hashes))!=4 or
                any(not isinstance(h,str) or len(h)!=64 or
                    any(c not in "0123456789abcdef" for c in h) for h in hashes)):
            raise ValueError("four unique DLMM signed transaction hashes required")
        provenance={"status":"INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
                    "source_slot":proof["source_slot"],
                    "source_digest":proof["source_sha256"],
                    "signed_transaction_hashes":hashes,
                    "independent_receipt_sha256":hashlib.sha256(json.dumps(
                        proof,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
        old=registry_row.get("signed_provenance")
        if old is None:
            rows[indexed[key]]={**registry_row,"signed_provenance":provenance}
        elif old!=provenance:
            prior=registry_row.get("signed_provenance_history",[])
            if not isinstance(prior,list):
                raise ValueError("DLMM previous signed provenance history malformed")
            if provenance not in prior:
                rows[indexed[key]]={**registry_row,
                    "signed_provenance_history":[*prior,provenance]}
        accepted+=1
    if accepted<required_verified:
        raise ValueError("DLMM required distinct signed pools not available")
    return {**registry,"pools":rows},{"venue":"meteora_dlmm",
        "status":"DLMM_EXISTING_REGISTRY_SIGNED_VERIFIED",
        "signed_verified_pools":accepted,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("registry","source","sdk","signed","output","report"):
        p.add_argument("--"+name,required=True)
    p.add_argument("--required",type=int,default=1)
    args=p.parse_args()
    result,report=merge(json.loads(Path(args.registry).read_text()),
        json.loads(Path(args.source).read_text()),
        json.loads(Path(args.sdk).read_text()),
        json.loads(Path(args.signed).read_text()),
        required_verified=args.required)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    Path(args.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__=="__main__":
    main()
