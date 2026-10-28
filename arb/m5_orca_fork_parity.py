"""Hard Orca-only swap parity gate against independently signed fork receipts.

Never infer correctness from simulation booleans or a quote. The exact input,
terminal SPL delta and source-account bytes are jointly authenticated by the
existing signed acceptance assessment. No external RPC or live transaction.
"""
import json
from pathlib import Path
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_all_venue_signed_quotes import quote_leg
from arb.m5_four_to_six_source_signed_acceptance import assess

SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def compare_orca(fixture,receipts,*,observed_unix):
    if type(observed_unix) is not int or observed_unix<0:
        raise ValueError("fork observation clock required")
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("offline source fixture required")
    rows=extract_pool_states(fixture)
    indexes=[i for i,row in enumerate(rows) if row["venue"]=="orca"]
    if len(indexes)!=1:
        raise ValueError("exactly one Orca leg is required for isolated pricing parity")
    index=indexes[0]
    if index!=len(rows)-1:
        raise ValueError("Orca terminal leg required for signed SPL balance proof")
    if not isinstance(receipts,dict) or not receipts:
        raise ValueError("genuine per-size signed receipts missing")
    measured=[]
    for size,receipt in sorted(receipts.items()):
        if type(size) is not int or not 0<size<2**64 or not isinstance(receipt,dict):
            raise ValueError("invalid per-size signed inventory")
        verified=assess(fixture,receipt)
        if verified.get("status")!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK":
            raise ValueError("independent signed rollback acceptance absent at size "+str(size))
        inputs=receipt.get("planned_inputs")
        balances=receipt.get("positive_post_balances_base_units")
        if (not isinstance(inputs,list) or len(inputs)!=len(rows) or
                inputs[0]!=size or type(inputs[index]) is not int or
                not 0<inputs[index]<2**64 or not isinstance(balances,list)
                or len(balances)!=len(rows)+1 or
                any(type(b) is not int or b<0 for b in balances)):
            raise ValueError("signed Orca exact input or terminal balance absent")
        # assess() verifies the same-slot source manifest, signed CPI chain,
        # post-balances, positive/negative packets and atomic rollback.
        actual=balances[-1]
        quote=quote_leg(fixture,leg_index=index,amount_in=inputs[index],
                        observed_unix=observed_unix)
        if (any(quote.get(k) is not False for k in SAFE) or
                quote.get("venue")!="orca" or
                quote.get("pool")!=rows[index]["address"] or
                quote.get("source_slot")!=fixture["state_accounts_observed_slot"]):
            raise ValueError("Orca quote is not bound to authenticated source")
        predicted=quote.get("predicted_output_base_units")
        if quote.get("quote_status")!="SOURCE_BOUND_INDICATIVE" or type(predicted) is not int:
            raise ValueError("Orca native source model could not price signed input: "+
                             str(quote.get("reason","unknown")))
        measured.append({"initial_route_input_base_units":size,
                         "orca_input_base_units":inputs[index],
                         "orca_signed_terminal_output_base_units":actual,
                         "orca_native_output_base_units":predicted,
                         "signed_minus_native_base_units":actual-predicted,
                         "source_slot":fixture["state_accounts_observed_slot"],
                         "pool":rows[index]["address"],
                         "independent_signed_rollback_verified":True,**SAFE})
    mismatch=sum(r["signed_minus_native_base_units"]!=0 for r in measured)
    return {"status":("ORCA_FORK_SIGNED_NATIVE_PARITY_ALL_SIZES" if mismatch==0
                       else "ORCA_FORK_SIGNED_NATIVE_PARITY_MISMATCH"),
            "source_slot":fixture["state_accounts_observed_slot"],
            "pool":rows[index]["address"],"size_count":len(measured),
            "exact_match_count":len(measured)-mismatch,
            "mismatch_count":mismatch,"measurements":measured,
            "protocol_exact_for_all_pools_verified":False,**SAFE}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipts",required=True)
    p.add_argument("--observed-unix",type=int,required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amounts",default="10000,100000,1000000")
    a=p.parse_args()
    amounts=[int(v) for v in a.amounts.split(",")]
    root=Path(a.receipts)
    receipts={v:json.loads((root/("signed-size-"+str(v)+".json")).read_text()) for v in amounts}
    report=compare_orca(json.loads(Path(a.fixture).read_text()),receipts,
                        observed_unix=a.observed_unix)
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"size_count":report["size_count"],
                      "exact_match_count":report["exact_match_count"],**SAFE}))
    if report["mismatch_count"]:
        raise SystemExit("Orca signed fork output disagrees with native integer quote")

if __name__=="__main__":
    main()
