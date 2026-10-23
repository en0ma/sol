"""Eight-venue execution target; historical evidence is not a CI execution pass.

Separate pool decoding, instruction building, signed standalone simulation,
and ordered cross-venue atomic simulation. Never infer one gate from another.
"""
from itertools import permutations
import json

TARGET_VENUES=(
    "orca", "raydium_cpmm", "raydium_clmm", "meteora_dlmm",
    "meteora_damm_v2", "pumpswap", "raydium_amm_v4",
    "orca_token_swap_v1",
)

def execution_matrix():
    from arb.onchain_pool_discovery import VENUES
    from arb.venue_capabilities import SWAP_BUILDERS, SIGNED_SWAP_VENUES, ATOMIC_PAIR_EVIDENCE
    from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED

    recognized=set(VENUES)|set(RECOGNIZED_UNSUPPORTED.values())
    if set(TARGET_VENUES)!=recognized:
        raise ValueError("execution target and recognized venue registry disagree")
    rows=[]
    for venue in TARGET_VENUES:
        decoder=venue in VENUES
        builder=venue in SWAP_BUILDERS
        historical=venue in SIGNED_SWAP_VENUES
        rows.append({
            "venue":venue,
            "pool_decoder_implemented":decoder,
            "signed_swap_builder_implemented":builder,
            "historical_standalone_signed_simulation_evidence":historical,
            "current_run_standalone_execution_verified":False,
            "standalone_execution_ready_this_run":False,
        })
    ordered=[]
    for first,second in permutations(TARGET_VENUES,2):
        historical_pair=ATOMIC_PAIR_EVIDENCE.get(frozenset((first,second)))
        ordered.append({
            "first_venue":first,"second_venue":second,
            "both_decoders_implemented":first in VENUES and second in VENUES,
            "both_builders_implemented":first in SWAP_BUILDERS and second in SWAP_BUILDERS,
            "unordered_historical_pair_evidence":historical_pair,
            "this_execution_order_verified":False,
            "current_run_atomic_execution_verified":False,
            "intermediate_token_balance_verified":False,
            "rollback_verified":False,
        })
    return {
        "status":"EIGHT_VENUE_EXECUTION_TARGET_GAP_REPORT",
        "venue_target":len(TARGET_VENUES),
        "decoder_implemented":sum(r["pool_decoder_implemented"] for r in rows),
        "builder_implemented":sum(r["signed_swap_builder_implemented"] for r in rows),
        "historical_standalone_evidence":sum(r["historical_standalone_signed_simulation_evidence"] for r in rows),
        "current_run_standalone_verified":0,
        "unordered_pair_target":len(ordered)//2,
        "ordered_pair_target":len(ordered),
        "ordered_pair_verified":0,
        "venues":rows,"ordered_pairs":ordered,
        "historical_pair_evidence_is_not_ordered_execution_proof":True,
        "actionable":False,"live_execution_approved":False,"broadcast":False,
    }

def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=execution_matrix()
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({k:report[k] for k in (
        "status","venue_target","decoder_implemented","builder_implemented",
        "ordered_pair_target","ordered_pair_verified","broadcast")}))

if __name__=="__main__":
    main()
