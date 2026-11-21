"""Canonical PumpSwap pool identification from official Pump program PDA seeds.

The canonical creator is PDA(["pool-authority", base_mint], PUMP_PROGRAM).
It is NOT the pool's coin_creator field. Requires solders for real PDA
derivation; never silently classify a pool when derivation is unavailable.
"""
PUMP_PROGRAM="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


def classify_pool(state):
    from solders.pubkey import Pubkey
    if not isinstance(state,dict) or not isinstance(state.get("creator"),str):
        raise ValueError("missing pool creator")
    mint=Pubkey.from_string(state["base_mint"])
    creator=Pubkey.from_string(state["creator"])
    derived,_=Pubkey.find_program_address(
        [b"pool-authority",bytes(mint)],Pubkey.from_string(PUMP_PROGRAM))
    return {"canonical":creator==derived,"canonical_pool_verified":True,
            "expected_authority":str(derived),"creator":str(creator)}
