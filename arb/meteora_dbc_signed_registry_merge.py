"""Admit only independently signed DBC pools into one existing shared registry.

Does not modify working repository or execute trades. An explicit output
artifact is produced only when ALL original wire/Ed25519/raw SPL audits pass.
Six-pool completion is a separate required count, not inherited from CI green.
"""
import argparse,hashlib,json
from pathlib import Path
from arb.meteora_dbc_signed_audit import audit

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False,
      "registry_admission_approved":False}


def merge(registry,source,sdk,native,signed,*,required=1):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or type(required) is not int or not 1<=required<=6):
        raise ValueError("DBC existing registry and 1-6 independent signed pools required")
    accepted=audit(source,sdk,native,signed,required=required)
    if (accepted["independently_signed_verified_pools"]!=required or
            accepted.get("all_source_vault_poststates_reconciled") is not True):
        raise ValueError("DBC signed source vault verification prerequisite unmet")
    if source.get("status")=="SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY":
        source=source["source"]
    original={p["pool"]:p for p in source["source_pools"]}
    existing={(p.get("venue"),p.get("address")):i for i,p in enumerate(registry["pools"])}
    if len(existing)!=len(registry["pools"]):
        raise ValueError("DBC existing shared registry duplicate identities")
    rows=[dict(p) for p in registry["pools"]]
    for item in accepted["pools"]:
        addr=item["pool"]
        row=original[addr];f=row["pool_fields"]
        hashes=item["signed_transaction_hashes"]
        if item.get("source_vault_debit_credit_verified") is not True:
            raise ValueError("DBC full vault-backed signed pool evidence required")
        if (len(hashes)!=4 or len(set(hashes))!=4 or
            any(not isinstance(h,str) or len(h)!=64 or
                any(c not in "0123456789abcdef" for c in h) for h in hashes)):
            raise ValueError("DBC original four independent transaction hashes invalid")
        if (item["source_sha256"]!=row["accounts"][addr]["sha256"]
                or item["source_slot"]!=row["source_slot"]):
            raise ValueError("DBC source registry provenance mismatch")
        mints=[f["base_mint"],f["quote_mint"]]
        provenance={"status":"INDEPENDENT_DBC_ORIGINAL_SIGNED_NATIVE_SDK_SPL_PARITY",
          "source_slot":item["source_slot"],"source_digest":item["source_sha256"],
          "vault_debit_credit_verified":True,
          "two_signed_swaps_each_direction_verified":True,
          "signed_transaction_hashes":hashes,
          "independent_receipt_sha256":hashlib.sha256(
             json.dumps(item,sort_keys=True,separators=(",",":")).encode()).hexdigest()}
        key=("meteora_dbc",addr)
        if key not in existing:
            existing[key]=len(rows)
            rows.append({"venue":"meteora_dbc","address":addr,
                         "mints":mints,"signed_provenance":provenance,
                         "usable_for_arbitrage":False,
                         "requires_live_state_revalidation":True})
        else:
            previous=rows[existing[key]]
            # Even historically admitted identities lose usable status here:
            # a new signed artifact never substitutes for fresh pool pricing.
            if previous.get("usable_for_arbitrage") is True:
                rows[existing[key]]={**previous,
                    "usable_for_arbitrage":False,
                    "requires_live_state_revalidation":True}
                previous=rows[existing[key]]
            if previous.get("mints")!=mints:
                raise ValueError("DBC original registered mint identity changed")
            old=previous.get("signed_provenance")
            if old is None:
                rows[existing[key]]={**previous,"signed_provenance":provenance}
            elif old!=provenance:
                history=previous.get("signed_provenance_history",[])
                if not isinstance(history,list):
                    raise ValueError("DBC previous signed evidence history malformed")
                if provenance not in history:
                    rows[existing[key]]={**previous,
                       "signed_provenance_history":[*history,provenance]}
    return {**registry,"pools":rows},{"venue":"meteora_dbc",
        "status":"DBC_INDEPENDENT_SIGNED_SHARED_REGISTRY_ARTIFACT_ONLY",
        "signed_verified_pools_in_current_run":required,
        "target_signed_verified_pools":6,
        "usable_for_arbitrage":False,
        "requires_live_state_revalidation":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ("registry","source","sdk","native","signed","output","report"):
        p.add_argument("--"+n,required=True)
    p.add_argument("--required",type=int,default=1)
    a=p.parse_args()
    result,report=merge(*(json.loads(Path(getattr(a,n)).read_text())
        for n in ("registry","source","sdk","native","signed")),required=a.required)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    Path(a.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report))


if __name__=="__main__":main()
