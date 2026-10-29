"""Validate an independent PumpSwap SDK comparison without confusing it with signed parity.

The official SDK oracle produces candidate evidence only. Four SDK matches do
not prove execution; signed Surfpool output is a separate future acceptance gate.
"""
import json
from pathlib import Path


def audit(source, sdk):
    if (not isinstance(source,dict) or source.get("venue")!="pumpswap" or
            not isinstance(source.get("pools"),list) or
            not isinstance(sdk,dict) or sdk.get("venue")!="pumpswap" or
            not isinstance(sdk.get("pools"),list)):
        raise ValueError("invalid PumpSwap source or SDK report")
    if sdk.get("signed_parity_verified") is not False or sdk.get("actionable") is not False or (
            sdk.get("registry_admission_approved") is not False):
        raise ValueError("independent SDK output cannot certify signed execution")
    source_rows={r.get("address"):r for r in source["pools"]
                 if isinstance(r,dict) and isinstance(r.get("address"),str)}
    if len(source_rows)!=len(source["pools"]):
        raise ValueError("duplicate source pool identity")
    sdk_rows={r.get("address"):r for r in sdk["pools"]
              if isinstance(r,dict) and isinstance(r.get("address"),str)}
    if len(sdk_rows)!=len(sdk["pools"]) or set(sdk_rows)!=set(source_rows):
        raise ValueError("SDK pool identities disagree with authenticated sources")
    approved=0
    for address,receipt in sdk_rows.items():
        source_row=source_rows[address]
        if source_row.get("status")!="AUTHENTICATED_SOURCE_ONLY":
            raise ValueError("SDK receipt for unauthenticated source")
        if receipt.get("signed_parity_verified") is not False or receipt.get("actionable") is not False:
            raise ValueError("SDK receipt improperly promoted to signed proof")
        trials=receipt.get("trials")
        if not isinstance(trials,list) or len(trials)!=4:
            raise ValueError("four SDK comparisons required")
        observed=set()
        for row in trials:
            if row.get("signed_parity_verified") is not False:
                raise ValueError("SDK trial claims signed execution")
            size=row.get("amount_in")
            mint=row.get("input_mint")
            if type(size) is not int or size<=0 or not isinstance(mint,str):
                raise ValueError("SDK trial identity invalid")
            if (mint,size) in observed:
                raise ValueError("duplicate SDK input direction or size")
            observed.add((mint,size))
            if row.get("status")!="OFFICIAL_SDK_CANDIDATE_EXACT":
                raise ValueError("official SDK mismatch or unsupported pool")
            try:
                official=int(row["official_sdk_output"])
                local=int(row["python_candidate_output"])
            except (ValueError,KeyError,TypeError):
                raise ValueError("official SDK integer output missing") from None
            if official<=0 or local!=official:
                raise ValueError("independent SDK pricing disagreement")
        mints=source_row.get("mints")
        if not isinstance(mints,list) or len(mints)!=2 or len(set(mints))!=2:
            raise ValueError("missing authenticated pool mints")
        if any(sum(mint==key[0] for key in observed)!=2 for mint in mints):
            raise ValueError("SDK direction/size coverage incomplete")
        approved+=1
    if sdk.get("sdk_candidate_verified_pools")!=approved:
        raise ValueError("SDK report summary conflicts with exact comparisons")
    return {"venue":"pumpswap","sdk_candidate_matched_pools":approved,
            "status":"SDK_CANDIDATE_PRICE_PARITY_ONLY","signed_parity_verified":False,
            "registry_admission_approved":False,"actionable":False,"broadcast":False}


def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("sdk")
    p.add_argument("output")
    args=p.parse_args()
    summary=audit(json.loads(Path(args.source).read_text()),
                  json.loads(Path(args.sdk).read_text()))
    Path(args.output).write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps(summary))


if __name__=="__main__":
    main()
