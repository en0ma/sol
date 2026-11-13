"""Conservative venue capability catalog, based on code and historical CI evidence.

'atomic_pairings' contains observed pairs, NOT a complete compatibility matrix.
Having a builder never implies a quote, successful simulation or profitability.
"""
SWAP_BUILDERS=frozenset(("orca","raydium_cpmm","raydium_clmm","meteora_dlmm"))
SIGNED_SWAP_VENUES=frozenset(("orca","raydium_cpmm","raydium_clmm","meteora_dlmm"))
# Observed signed atomic instructions involving both programs, unordered.
ATOMIC_PAIR_EVIDENCE={
    frozenset(("orca","raydium_cpmm")):"cross-venue-size-sweep / reverse-cross-venue-sweep",
    frozenset(("raydium_cpmm","raydium_clmm")):"raydium-clmm-swap-attempt",
    frozenset(("orca","meteora_dlmm")):"orca-meteora-isolated-atomic-simulation",
}
# Pair-specific closed SOL cycles independently demonstrated.
CLOSED_CYCLE_EVIDENCE={
    ("orca","raydium_cpmm"):"cross-venue-size-sweep",
    ("raydium_cpmm","orca"):"reverse-cross-venue-sweep",
    ("meteora_dlmm","orca"):"orca-meteora-isolated-atomic-simulation",
}
def venue_capabilities(venue):
    return {"swap_instruction_builder":venue in SWAP_BUILDERS,
            "signed_swap_simulated_historically":venue in SIGNED_SWAP_VENUES,
            "generalized_atomic_assembler_supported":venue in SWAP_BUILDERS,
            "arbitrary_atomic_pair_verified":False,
            "profitable_live_execution_verified":False,
            "broadcast":False}
def atomic_pair_matrix():
    return [{"venues":sorted(pair),"atomic_simulation_evidence":source,
             "closed_cycle_orders_verified":[list(k) for k in CLOSED_CYCLE_EVIDENCE
                 if frozenset(k)==pair]}
            for pair,source in sorted(ATOMIC_PAIR_EVIDENCE.items(),
                                    key=lambda entry:tuple(sorted(entry[0])))]

def complete_pair_matrix(venues=None):
    """Report each unordered pair, with explicit historical-evidence boundaries."""
    selected=tuple(sorted(venues if venues is not None else SWAP_BUILDERS))
    rows=[]
    for i,left in enumerate(selected):
        for right in selected[i+1:]:
            pair=frozenset((left,right))
            evidence=ATOMIC_PAIR_EVIDENCE.get(pair)
            closed=[{"order":list(order),"artifact_name":source}
                    for order,source in sorted(CLOSED_CYCLE_EVIDENCE.items())
                    if frozenset(order)==pair]
            rows.append({"venues":[left,right],
                "both_builders_available":left in SWAP_BUILDERS and right in SWAP_BUILDERS,
                "historical_signed_atomic_pair_verified":evidence is not None,
                "historical_atomic_evidence_artifact":evidence,
                "closed_cycle_orders_verified":closed,
                "current_ci_run_pair_simulated":False,
                "arbitrary_pairing_approved":False,"actionable":False,"broadcast":False})
    return {"status":"HISTORICAL_PAIRWISE_ATOMIC_EVIDENCE",
        "venue_count":len(selected),"pairs":rows,
        "historical_verified_pairs":sum(bool(row["historical_signed_atomic_pair_verified"]) for row in rows),
        "current_ci_run_pair_simulated":False,
        "profitable_live_execution_verified":False,"actionable":False,"broadcast":False}

def main():
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    report=complete_pair_matrix()
    Path(args.output).write_text(json.dumps(report,indent=2))
    print(json.dumps({"status":report["status"],"pairs":len(report["pairs"]),
        "historical_verified_pairs":report["historical_verified_pairs"],
        "current_ci_run_pair_simulated":False,"broadcast":False}))
if __name__=="__main__":
    main()
