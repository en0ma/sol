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
