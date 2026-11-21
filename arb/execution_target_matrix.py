"""Seven-active-venue execution target; historical evidence is not a CI execution pass.

Separate pool decoding, instruction building, signed standalone simulation,
and ordered cross-venue atomic simulation. Never infer one gate from another.
"""
from itertools import permutations
import ast
import json
from pathlib import Path

TARGET_VENUES=(
    "orca", "raydium_cpmm", "raydium_clmm", "meteora_dlmm",
    "meteora_damm_v2", "pumpswap", "raydium_amm_v4",
)

def execution_matrix():
    from arb.eight_venue_onchain_probe import BUILDERS, LEGACY
    from arb.onchain_pool_discovery import VENUES
    from arb.venue_capabilities import SIGNED_SWAP_VENUES, ATOMIC_PAIR_EVIDENCE
    from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED
    ARCHIVED_VENUES=frozenset({"orca_token_swap_v1"})

    recognized=set(VENUES)|set(RECOGNIZED_UNSUPPORTED.values())
    if set(TARGET_VENUES)!=(recognized-ARCHIVED_VENUES):
        raise ValueError("execution target and recognized venue registry disagree")
    # Parse source instead of importing runtime modules: offline CI does not
    # install solders. Syntax-level inventory is NOT execution proof.
    def has_function(module,names):
        path=Path(__file__).resolve().parents[1].joinpath(*module.split(".")).with_suffix(".py")
        if not path.is_file():
            return False
        tree=ast.parse(path.read_text())
        defined={node.name for node in tree.body
                 if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))}
        return bool(defined.intersection(names))
    decoder_present={venue:(venue in VENUES or
        has_function(LEGACY[venue][0],{"decode"}))
        for venue in TARGET_VENUES}
    builder_names={"build","instruction","build_swap","build_swap2",
                   "build_swap_v2","build_instruction"}
    builder_present={venue:has_function(BUILDERS[venue],builder_names)
                     for venue in TARGET_VENUES}
    rows=[]
    for venue in TARGET_VENUES:
        decoder=decoder_present[venue]
        builder=builder_present[venue]
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
            "both_decoders_implemented":decoder_present[first] and decoder_present[second],
            "both_builders_implemented":builder_present[first] and builder_present[second],
            "unordered_historical_pair_evidence":historical_pair,
            "this_execution_order_verified":False,
            "current_run_atomic_execution_verified":False,
            "intermediate_token_balance_verified":False,
            "rollback_verified":False,
        })
    return {
        "status":"SEVEN_VENUE_EXECUTION_TARGET_GAP_REPORT",
        "venue_target":len(TARGET_VENUES),
        "archived_optional_venues":sorted(ARCHIVED_VENUES),
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
