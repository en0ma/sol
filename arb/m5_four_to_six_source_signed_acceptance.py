"""Independently audit a source-authenticated signed 4–6-leg local-fork receipt.

Accepts only a signed receipt from the actual adaptive coordinator with the
same manifest, slot, pool order, mint path, positive SPL/CPI flow, and final
swap rollback. Never infers a profit or an executable trading opportunity.
"""
import ast
import json
from pathlib import Path
from arb.source_snapshot_manifest import verify
from arb.fixture_quote_execution_pipeline import extract_pool_states
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def assess(fixture,receipt):
    verify(fixture)
    if (fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE"
            or any(fixture.get(k)is not False for k in SAFE)):
        raise ValueError("safe authenticated source route required")
    rows=extract_pool_states(fixture)
    n=len(rows)
    if not 4<=n<=6:raise ValueError("four-to-six source legs required")
    errors=[]
    if not isinstance(receipt,dict):
        receipt={}
        errors.append("signed receipt missing")
    for key in SAFE:
        if receipt.get(key) is not False:errors.append("unsafe signed receipt "+key)
    required={
        "status":"SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED",
        "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
        "fixture_kind":fixture["fixture_kind"],
        "legs":n,
        "route_venues":fixture["route_venues"],
        "route_pool_addresses":fixture["route_pool_addresses"],
        "route_mints":fixture["route_mints"],
        "state_accounts_observed_slot":fixture["state_accounts_observed_slot"],
        "state_account_manifest_sha256":fixture["state_account_manifest_sha256"],
        "signed_cpi_per_leg_verified":True,
        "rollback_failure_case_verified":True,
        "signed_atomic_simulation_verified":True,
        "quote_accuracy_verified":False,
    }
    for key,expected in required.items():
        if receipt.get(key)!=expected:errors.append("inconsistent signed receipt "+key)
    if receipt.get("source_snapshot_slot") is not None:
        errors.append("fork readback cannot attest original mainnet source slot")
    amounts=receipt.get("planned_inputs")
    if (not isinstance(amounts,list) or len(amounts)!=n or
            any(type(x)is not int or not 0<x<2**64 for x in amounts)):
        errors.append("invalid declared signed amounts")
        amounts=None
    start=receipt.get("initial_balances_base_units")
    if (not isinstance(start,list) or len(start)!=n+1 or
            amounts is None or start!=[amounts[0]]+[0]*n):
        errors.append("initial SPL accounts or source-funded test amounts not authenticated")
    after=receipt.get("positive_post_balances_base_units")
    if (not isinstance(after,list) or len(after)!=n+1 or
            any(type(x)is not int or x!=0 for x in after[:-1]) or
            type(after[-1]) is not int or after[-1]<=0):
        errors.append("positive SPL post-balance continuity missing")
    hops=receipt.get("cpi_hops")
    if not isinstance(hops,list) or len(hops)!=n-1 or amounts is None:
        errors.append("independent intermediate CPI hop count incomplete")
    else:
        seen=set()
        for i,hop in enumerate(hops,1):
            if (not isinstance(hop,dict) or hop.get("hop")!=i
                    or type(hop.get("account"))is not str or not hop["account"]
                    or hop["account"] in seen
                    or any(hop.get(field)!=amounts[i] for field in
                           ("planned_input_base_units","received_base_units",
                            "consumed_base_units"))):
                errors.append("independent signed SPL/CPI continuity hop "+str(i))
            if isinstance(hop,dict) and isinstance(hop.get("account"),str):
                seen.add(hop["account"])
    packet=receipt.get("signed_packet_bytes")
    if type(packet)is not int or not 100<=packet<=1232:
        errors.append("actual signed Solana packet size unverified")
    negative=receipt.get("negative_error")
    try:
        error=ast.literal_eval(negative)
        idx=error["InstructionError"][0]
    except (ValueError,TypeError,SyntaxError,KeyError,IndexError,AttributeError):
        idx=None
    if type(idx)is not int or idx!=n-1 or receipt.get("negative_failure_instruction_index")!=idx:
        errors.append("negative final-leg control did not fail exactly on last swap")
    if type(receipt.get("negative_packet_bytes"))is not int:
        errors.append("negative signed rollback packet missing")
    # A superficially green receipt must include actual fork readback.
    hydrated=receipt.get("hydrated_fork_state_readback")
    if (not isinstance(hydrated,dict) or
            hydrated.get("status")!="HYDRATED_FORK_ACCOUNT_BYTES_MATCH" or
            hydrated.get("captured_source_slot")!=fixture["state_accounts_observed_slot"] or
            hydrated.get("source_mainnet_slot_independently_attested") is not False or
            type(hydrated.get("accounts_checked")) is not int or
            hydrated["accounts_checked"]<=0 or
            type(hydrated.get("fork_readback_slot")) is not int or
            any(hydrated.get(key) is not False for key in SAFE)):
        errors.append("independent hydrated source-fork readback missing or mismatched")
    # No origin or profitability can be inferred from simulation's synthetic
    # user test token balances or from unsigned indicative source quotes.
    return {"status":"VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK" if not errors
                else "SOURCE_FOUR_TO_SIX_SIGNED_ROLLBACK_UNVERIFIED",
            "hops":n,"source_slot":fixture["state_accounts_observed_slot"],
            "route_pool_addresses":fixture["route_pool_addresses"],
            "route_mints":fixture["route_mints"],
            "source_manifest_sha256":fixture["state_account_manifest_sha256"],
            "failure_reasons":errors,
            "signed_atomic_simulation_verified":not errors,
            "rollback_failure_case_verified":not errors,
            "net_profit_verified":False,
            "live_execution_approved":False,"actionable":False,"broadcast":False}

def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--receipt",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    fixture=json.loads(Path(args.fixture).read_text())
    receipt=json.loads(Path(args.receipt).read_text())
    result=assess(fixture,receipt)
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":result["status"],"failure_reasons":result["failure_reasons"],**SAFE}))
if __name__=="__main__":main()
