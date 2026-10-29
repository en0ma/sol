"""Existing registry sixth-venue signed admission gate.

The only way Raydium CLMM becomes a signed-verified registry member is
an independent post-hoc verifier of original signed SwapV2 transactions
against same-slot authenticated source/native integer/official SDK/SPL bytes.
No new coordinator, no broadcast.
"""
import argparse,hashlib,json
from pathlib import Path
from arb.raydium_clmm_sixth_signed_audit import audit
from arb.raydium_clmm import decode
import base64

SAFE={"actionable":False,"broadcast":False,
      "live_execution_approved":False,"registry_admission_approved":False}

def merge(registry,tick_source,sdk,signed,*,required=1):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or type(required) is not int or not 1<=required<=3):
        raise ValueError("existing bounded source registry required")
    independent=audit(tick_source,sdk,signed)
    if independent["verified_pools"]<required:
        raise ValueError("CLMM fewer than required independently audited signed pools")
    indexed={(p.get("venue"),p.get("address")):i for i,p in enumerate(registry["pools"])}
    if len(indexed)!=len(registry["pools"]):
        raise ValueError("registered pool duplicate identities")
    sources={p["pool"]:p for p in tick_source["pools"]}
    updated=[dict(row) for row in registry["pools"]]
    accepted=0
    for verified in independent["pools"]:
        address=verified["pool"]
        key=("raydium_clmm",address)
        source=sources.get(address)
        if source is None:
            raise ValueError("CLMM signed pool missing independently audited onchain source")
        original=source["tick_capture"]["synchronized_non_tick_accounts"][0]
        decoded=decode(base64.b64decode(original["account_base64"],validate=True))
        mints=[decoded["token_mint_0"],decoded["token_mint_1"]]
        if key in indexed:
            existing=updated[indexed[key]]
            if existing.get("mints")!=mints:
                raise ValueError("CLMM signed pool mints disagree with original registry")
        else:
            existing={"venue":"raydium_clmm","address":address,"mints":mints}
            updated.append(existing)
            indexed[key]=len(updated)-1
        if (verified["source_digest"]!=source["tick_snapshot_sha256"]
            or verified["source_slot"]!=source["tick_capture"]["tick_array_source_slot"]):
            raise ValueError("CLMM signed source provenance changed")
        tx=verified["signed_transaction_hashes"]
        if (len(tx)!=4 or len(set(tx))!=4 or
            any(not isinstance(t,str) or len(t)!=64 or
                any(c not in "0123456789abcdef" for c in t) for t in tx)):
            raise ValueError("CLMM four unique verified transactions absent")
        canon=json.dumps(verified,sort_keys=True,separators=(",",":"))
        proof={"status":"INDEPENDENT_CLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
            "source_slot":verified["source_slot"],
            "source_digest":verified["source_digest"],
            "signed_transaction_hashes":tx,
            "independent_receipt_sha256":hashlib.sha256(canon.encode()).hexdigest()}
        prior=existing.get("signed_provenance")
        if prior is None:
            updated[indexed[key]]={**existing,"signed_provenance":proof}
        elif prior!=proof:
            history=existing.get("signed_provenance_history",[])
            if not isinstance(history,list):
                raise ValueError("CLMM prior immutable proof history malformed")
            if proof not in history:
                updated[indexed[key]]={**existing,
                    "signed_provenance_history":[*history,proof]}
        accepted+=1
    return {**registry,"pools":updated},{"venue":"raydium_clmm",
        "status":"RAYDIUM_CLMM_SIGNED_REGISTRY_PROVENANCE_ACCEPTED",
        "signed_verified_pools":accepted,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("registry","tick-source","sdk","signed","output","report"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    out,receipt=merge(json.loads(Path(a.registry).read_text()),
        json.loads(Path(a.tick_source).read_text()),
        json.loads(Path(a.sdk).read_text()),
        json.loads(Path(a.signed).read_text()))
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n")
    Path(a.report).write_text(json.dumps(receipt,indent=2)+"\n")
    print(json.dumps(receipt))
if __name__=="__main__":main()
