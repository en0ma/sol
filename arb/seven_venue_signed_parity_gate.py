"""Seven-venue signed-fork price parity accounting and acceptance gates.

Empirical source snapshots are *not* proof of protocol exactness. A venue earns
quote evidence only for an independently accepted signed CPI observation with
a real integer output and an independently computed native predicted output.
Unknown venues, missing receipts and blocked legs never become zero-error rows.
"""
import json
from pathlib import Path
from arb.fixture_all_venue_signed_quotes import VENUES

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
ORDER=("orca","raydium_cpmm","raydium_clmm","meteora_dlmm",
       "meteora_damm_v2","pumpswap","raydium_amm_v4")
if set(ORDER)!=VENUES or len(ORDER)!=7:
    raise RuntimeError("seven-venue pricing registry out of sync")

def summarize(samples,*,strict=False):
    if not isinstance(samples,list):
        raise ValueError("signed parity observations must be a list")
    rows={v:{"venue":v,"observed":0,"compared":0,"exact":0,
             "mismatched":0,"blocked":0,"largest_integer_error":None,
             "block_reasons":{},"protocol_exact_verified":False,**SAFE}
          for v in ORDER}
    for s in samples:
        if not isinstance(s,dict) or s.get("venue") not in rows:
            raise ValueError("signed sample unknown or malformed venue")
        row=rows[s["venue"]]
        status=s.get("sample_status")
        if status=="SAMPLE_BLOCKED":
            # Never accept a supposed blocked observation that also asserts
            # integer parity or a protocol-exact pricing verdict.
            if (s.get("exact_integer_match") is not None or
                    s.get("integer_delta_base_units") is not None or
                    s.get("source_exact_protocol_verified") is True):
                raise ValueError("blocked venue sample contains forged parity evidence")
            row["blocked"]+=1
            reason=s.get("reason") or "UNKNOWN_NATIVE_SOURCE_BLOCKER"
            reason=str(reason)[:160]
            row["block_reasons"][reason]=row["block_reasons"].get(reason,0)+1
            continue
        if status!="SIGNED_FORK_QUOTE_COMPARISON":
            raise ValueError("unsupported signed pricing sample status")
        if s.get("actionable",False) is not False or s.get("broadcast",False) is not False:
            raise ValueError("unsafe signed experiment row")
        if s.get("signed_simulation_accepted") is not True:
            raise ValueError("unaccepted signed simulation cannot be counted")
        observed=s.get("signed_output_base_units")
        predicted=s.get("predicted_output_base_units")
        amount=s.get("signed_input_base_units")
        slot=s.get("source_slot")
        manifest=s.get("source_manifest_sha256")
        if (type(observed)is not int or observed<=0 or
                type(predicted)is not int or predicted<=0 or
                type(amount)is not int or amount<=0 or
                type(slot)is not int or slot<0 or
                not isinstance(manifest,str) or len(manifest)!=64):
            raise ValueError("comparison missing source-bound signed integer provenance")
        delta=observed-predicted
        if (s.get("absolute_integer_error_base_units") not in (None,abs(delta)) or
                s.get("integer_delta_base_units")!=delta or
                s.get("exact_integer_match") is not (delta==0) or
                s.get("source_exact_protocol_verified") is not False):
            raise ValueError("comparison delta or protocol exactness misrepresented")
        row["observed"]+=1
        row["compared"]+=1
        row["exact" if delta==0 else "mismatched"]+=1
        error=abs(delta)
        row["largest_integer_error"]=max(row["largest_integer_error"] or 0,error)
    complete=all(rows[v]["compared"]>0 and rows[v]["mismatched"]==0
                 for v in ORDER)
    report={"status":"ALL_SEVEN_INDICATIVE_INTEGER_PARITY" if complete else
                    "SEVEN_VENUE_PRICING_EVIDENCE_INCOMPLETE",
            "venue_order":list(ORDER),"by_venue":rows,
            "venue_coverage_count":sum(rows[v]["compared"]>0 for v in ORDER),
            "signed_comparisons":sum(x["compared"] for x in rows.values()),
            "exact_integer_matches":sum(x["exact"] for x in rows.values()),
            "integer_mismatches":sum(x["mismatched"] for x in rows.values()),
            "full_seven_venue_protocol_exact_verified":False,**SAFE}
    if strict and not complete:
        raise ValueError("seven venue signed quote parity incomplete")
    return report

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--strict",action="store_true")
    a=parser.parse_args()
    data=json.loads(Path(a.input).read_text())
    report=summarize(data["samples"])
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],
                      "venue_coverage_count":report["venue_coverage_count"],
                      "signed_comparisons":report["signed_comparisons"],
                      "integer_mismatches":report["integer_mismatches"],
                      "broadcast":False}))
    if a.strict and report["venue_coverage_count"]!=7:
        raise SystemExit("seven-venue parity lacks independently compared venue samples")
if __name__=="__main__":main()
