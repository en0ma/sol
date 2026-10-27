"""Audit each actual signed four-to-six-hop size independently against source.

Consumes files produced by the existing genuine offline signed engine. Never
accepts a boolean receipt without source identity, explicit signed packet
identifiers, prefix SPL continuity and rollback preconditions.
"""
import json
from pathlib import Path
from arb.m5_four_to_six_source_signed_acceptance import assess
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def audit_attempts(fixture,receipts,*,expected_amounts):
    if (not isinstance(receipts,dict) or
            not isinstance(expected_amounts,(list,tuple)) or
            not 1<=len(expected_amounts)<=8 or
            len(set(expected_amounts))!=len(expected_amounts) or
            any(type(x)is not int or not 0<x<2**64 for x in expected_amounts)):
        raise ValueError("bounded source signed amount inventory required")
    attempts=[]
    accepted=[]
    signed_gross_observations=[]
    for size in expected_amounts:
        receipt=receipts.get(size)
        if not isinstance(receipt,dict):
            receipt={"status":"SIGNATURE_OR_TRIAL_MISSING",**SAFE}
        verified=assess(fixture,receipt)
        inputs=receipt.get("planned_inputs")
        if (not isinstance(inputs,list) or not inputs or
                type(inputs[0])is not int or inputs[0]!=size):
            verified["failure_reasons"].append("signed starting input mismatches size")
            verified["status"]="SOURCE_FOUR_TO_SIX_SIGNED_ROLLBACK_UNVERIFIED"
            verified["signed_atomic_simulation_verified"]=False
            verified["rollback_failure_case_verified"]=False
        approved=verified["status"]=="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK"
        if approved:accepted.append(size)
        # The source-bound independent audit establishes that the transaction
        # actually consumed the full starting amount, left no intermediate
        # user balances, and credited the final account. Gross deltas are
        # observations from signed isolated simulation, never fee-adjusted
        # arbitrage opportunities or live execution approvals.
        signed_gross=None
        if approved:
            post=receipt.get("positive_post_balances_base_units")
            if (isinstance(post,list) and len(post)==verified.get("hops",0)+1
                    and all(type(v)is int and v>=0 for v in post)
                    and all(v==0 for v in post[:-1])):
                signed_gross=post[-1]-size
                signed_gross_observations.append({
                    "size_base_units":size,"terminal_output_base_units":post[-1],
                    "gross_start_mint_delta_base_units":signed_gross,
                    "signed_compute_units":receipt.get("positive_units_consumed"),
                    "signed_message_fee":receipt.get("signed_message_fee_estimate"),
                    "source_manifest_sha256":verified.get("source_manifest_sha256"),
                    "net_profit_verified":False,**SAFE})
        attempts.append({"size_base_units":size,"receipt_status":receipt.get("status"),
                         "audit":verified,"independently_accepted":approved,
                         "observed_gross_start_mint_delta_base_units":signed_gross,
                         "net_profit_verified":False,**SAFE})
    gross_ranking=sorted(signed_gross_observations,
        key=lambda x:(-x["gross_start_mint_delta_base_units"],x["size_base_units"]))
    return {"status":"FOUR_TO_SIX_SOURCE_SIGNED_MULTISIZE_INDEPENDENT_AUDIT",
            "attempts":attempts,"attempt_count":len(attempts),
            "independently_accepted_amounts_base_units":accepted,
            "independently_accepted_count":len(accepted),
            "signed_gross_observation_count":len(signed_gross_observations),
            "signed_gross_only_research_ranking":gross_ranking,
            "positive_signed_gross_count":sum(x["gross_start_mint_delta_base_units"]>0
                                              for x in gross_ranking),
            "starting_mint":fixture.get("route_mints",[None])[0],
            "ranked_net_profitable_candidates":[],
            "net_profit_verified":False,
            "protocol_exact_seven_venue_parity_verified":False,**SAFE}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipts",required=True)
    p.add_argument("--amounts",default="10000,100000,1000000")
    p.add_argument("--output",required=True)
    a=p.parse_args()
    amounts=tuple(int(v) for v in a.amounts.split(","))
    root=Path(a.receipts)
    receipts={}
    for amount in amounts:
        file=root/("signed-size-"+str(amount)+".json")
        try:
            receipts[amount]=json.loads(file.read_text())
        except (OSError,ValueError):
            receipts[amount]={"status":"SIGNATURE_OR_TRIAL_MISSING",**SAFE}
    report=audit_attempts(json.loads(Path(a.fixture).read_text()),
        receipts,expected_amounts=amounts)
    Path(a.output).write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
        "independently_accepted_count":report["independently_accepted_count"],
        "attempt_count":report["attempt_count"],"broadcast":False}))
if __name__=="__main__":main()
