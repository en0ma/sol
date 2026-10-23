"""Fail CI on missing/malformed read-only venue evidence, not on coverage gaps.

This check cannot convert a decoder or builder to signed execution proof.
"""
import argparse
import json
from pathlib import Path
from arb.execution_target_matrix import TARGET_VENUES

def validate(report):
    if not isinstance(report,dict) or report.get("status")!="EIGHT_VENUE_ONCHAIN_READONLY_PROBE":
        raise ValueError("wrong eight-venue probe status")
    for flag in ("actionable","live_execution_approved","broadcast"):
        if report.get(flag) is not False:
            raise ValueError(flag+" must be false")
    rows=report.get("venues")
    if not isinstance(rows,list) or len(rows)!=len(TARGET_VENUES):
        raise ValueError("expected eight venue rows")
    if tuple(row.get("venue") for row in rows if isinstance(row,dict))!=TARGET_VENUES:
        raise ValueError("venue identities/order do not match target")
    decoder=builder=0
    for row in rows:
        for flag in ("decoder_onchain_verified","builder_code_present",
                     "builder_onchain_execution_verified"):
            if type(row.get(flag)) is not bool:
                raise ValueError("missing boolean gate "+flag+" for "+row["venue"])
        if row["builder_onchain_execution_verified"]:
            raise ValueError("read-only probe must not claim signed swap execution")
        if not isinstance(row.get("candidates_checked"),int) or row["candidates_checked"]<0:
            raise ValueError("invalid candidate count")
        if not isinstance(row.get("errors"),list):
            raise ValueError("missing error list")
        evidence=row.get("pool_evidence")
        if row["decoder_onchain_verified"]!=(isinstance(evidence,dict) and evidence.get("pool_decoder_verified") is True):
            raise ValueError("decoder verification disagrees with evidence")
        decoder+=row["decoder_onchain_verified"]
        builder+=row["builder_code_present"]
    if (report.get("decoder_verified_count")!=decoder
            or report.get("builder_code_count")!=builder
            or report.get("builder_execution_verified_count")!=0):
        raise ValueError("aggregate counts disagree with venue gates")
    return {"status":"VALID_READONLY_EVIDENCE","decoder_verified_count":decoder,
            "builder_code_count":builder,"signed_execution_verified_count":0,
            "broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    args=parser.parse_args()
    print(json.dumps(validate(json.loads(Path(args.input).read_text()))))

if __name__=="__main__":
    main()
