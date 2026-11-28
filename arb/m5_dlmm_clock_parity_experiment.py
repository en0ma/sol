"""Isolated signed DLMM Clock experiment using a pinned authenticated source fixture.

Compares the SAME source route with native offline Clock and a verified
forward-only Surfpool jump to the source snapshot slot. No broadcast and no
normal three-hop execution admission are changed by this experiment.
"""
import argparse
import json
import os
from pathlib import Path

AFFECTED_POOL="3msVd34R5KxonDzyNSV5nT19UtUeJ2RF1NaQhvVPNLxL"
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def target_source_slot(fixture):
    from arb.meteora_dlmm import decode
    from arb.next_ten_fork_pool_probe import PROGRAMS
    from base64 import b64decode
    pool=AFFECTED_POOL
    if (fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL"
            or fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE"
            or any(fixture.get(k)is not False for k in SAFE)
            or pool not in fixture.get("route_pool_addresses",[])):
        raise ValueError("expected pinned authenticated affected-pool fixture")
    account=fixture["accounts"][pool]
    if account.get("owner")!=PROGRAMS["meteora_dlmm"]:
        raise ValueError("DLMM fixture program owner differs")
    state=decode(b64decode(account["data"][0],validate=True))
    if state["pair_type"]!=1 or state["activation_type"]!=0:
        raise ValueError("target DLMM not permissioned slot-activated")
    slot=fixture.get("state_accounts_observed_slot")
    if type(slot)is not int or slot<=state["activation_point"]:
        raise ValueError("source slot not past DLMM activation point")
    return slot,{"pool":pool,"pair_type":state["pair_type"],
                 "status":state["status"],"activation_type":state["activation_type"],
                 "activation_point":state["activation_point"]}

def summarize_receipt(receipt):
    return {"receipt_status":receipt.get("status"),
            "signed_packet_crypto_bound":receipt.get("signed_packet_crypto_bound") is True,
            "signed_atomic_simulation_verified":receipt.get("signed_atomic_simulation_verified") is True,
            "rollback_failure_case_verified":receipt.get("rollback_failure_case_verified") is True,
            "positive_error":receipt.get("positive_error"),
            "positive_program_log_tail":[str(x)[:240] for x in
                (receipt.get("positive_logs") or [])[-10:]]}

def experiment(rpc,fixture,amount=100000):
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.rpc import call
    from arb.next_ten_fork_pool_probe import source_clock
    from arb.next_ten_signed_atomic_offline import run_four_to_six_venue
    from arb.source_snapshot_manifest import verify
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1" or os.environ.get("SURFPOOL_DATASOURCE_RPC_URL"):
        raise ValueError("isolated, source-disconnected Surfpool required")
    if type(amount)is not int or not 0<amount<2**64:
        raise ValueError("positive u64 input required")
    verify(fixture)
    source_slot,pool=target_source_slot(fixture)
    before=source_clock(rpc)
    report={"experiment":"DLMM_PERMISSIONED_CLOCK_PARITY_SIGNED_OFFLINE",
            "source_slot":source_slot,"pool":pool,"offline_clock_before":before,**SAFE}
    def attempt():
        try:
            receipt=run_four_to_six_venue(rpc,fixture,amount_in=amount,
                                          ephemeral_source_registry=True)
            return summarize_receipt(receipt)
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            return {"status":"REJECTED_OR_ABORTED","diagnostic":(type(exc).__name__+": "+str(exc))[:1000],
                    "signed_atomic_simulation_verified":False,
                    "rollback_failure_case_verified":False}
    report["before_clock_alignment"]=attempt()
    if before["slot"]>=source_slot:
        report["clock_alignment"]="NOT_POSSIBLE_FORWARD_ONLY_ALREADY_AT_OR_ABOVE_SOURCE"
        report["after_clock_alignment"]={"status":"NOT_ATTEMPTED"}
        return report
    travel=call(rpc,"surfnet_timeTravel",[{"absoluteSlot":source_slot}])
    after=source_clock(rpc)
    report["time_travel_response"]=travel
    report["offline_clock_after"]=after
    if after["slot"]<source_slot or after["slot"]<=before["slot"]:
        raise ValueError("Surfpool time travel did not advance authenticated Clock sysvar")
    report["clock_alignment"]="FORWARD_SLOT_PARITY_CONFIRMED"
    report["after_clock_alignment"]=attempt()
    return report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--fixture",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    fixture=json.loads(Path(a.fixture).read_text())
    report=experiment(a.rpc,fixture)
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:v for k,v in report.items() if k not in ("time_travel_response",)}))
    if report.get("clock_alignment")!="FORWARD_SLOT_PARITY_CONFIRMED":
        raise SystemExit("Clock parity experiment could not confirm source slot")

if __name__=="__main__":
    main()
