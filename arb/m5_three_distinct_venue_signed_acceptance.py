"""Independent admission gate for authentic three-distinct-venue Surfpool receipts."""
import json
import sys
from pathlib import Path

def verify(source,receipt):
    if (source.get("fixture_kind")!="THREE_DISTINCT_VENUE_CLOSED_ROUTE"
            or source.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL"):
        raise ValueError("untrusted distinct-venue source fixture")
    venues=source.get("route_venues")
    pools=source.get("route_pool_addresses")
    mints=source.get("route_mints")
    if (not isinstance(venues,list) or not isinstance(pools,list)
            or not isinstance(mints,list) or len(venues)!=len(pools)!=3
            or len(mints)!=4 or len(set(venues))!=3 or len(set(pools))!=3
            or len(set(mints[:3]))!=3 or mints[0]!=mints[-1]):
        raise ValueError("source route not a genuine distinct-venue triangle")
    from arb.source_snapshot_manifest import verify as verify_manifest
    verify_manifest(source)
    if (receipt.get("status")!="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"
            or receipt.get("legs")!=3
            or receipt.get("route_venues")!=venues
            or receipt.get("route_pool_addresses")!=pools
            or receipt.get("route_mints")!=mints
            or receipt.get("state_account_manifest_sha256")!=source["state_account_manifest_sha256"]
            or receipt.get("signed_cpi_per_leg_verified") is not True
            or receipt.get("signed_atomic_simulation_verified") is not True
            or receipt.get("rollback_failure_case_verified") is not True
            or receipt.get("negative_failure_instruction_index")!=2
            or receipt.get("actionable") is not False
            or receipt.get("live_execution_approved") is not False
            or receipt.get("broadcast") is not False):
        raise ValueError("signed three-venue CPI/rollback proof incomplete")
    amounts=receipt.get("planned_inputs")
    post=receipt.get("positive_post_balances_base_units")
    if (not isinstance(amounts,list) or len(amounts)!=3
            or any(type(a)is not int or a<=0 for a in amounts)
            or not isinstance(post,list) or len(post)!=4
            or post[1:3]!=[0,0] or type(post[3]) is not int or post[3]<=0):
        raise ValueError("intermediate consumption or final output unverified")
    return {"accepted":True,"three_distinct_venues":True,
            "signed_cpi_and_rollback":True,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def main():
    if len(sys.argv)!=3:raise SystemExit("usage: source.json signed-receipt.json")
    result=verify(json.loads(Path(sys.argv[1]).read_text()),
                  json.loads(Path(sys.argv[2]).read_text()))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__":main()
