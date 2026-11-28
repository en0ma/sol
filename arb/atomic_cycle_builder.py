"""Compose one signed, bounded multi-hop transaction for localhost simulation.

Each leg is an already-authenticated solders Instruction constructed by its
venue-specific builder. No router authority or external submission is added.
"""
from arb.pumpswap_local_simulation import local_rpc_only

def sign_atomic(rpc,payer,legs,setup=()):
    local_rpc_only(rpc)
    if not isinstance(legs,(list,tuple)) or not 2<=len(legs)<=4:
        raise ValueError("atomic route must have two to four legs")
    if not isinstance(setup,(list,tuple)) or len(setup)>8:
        raise ValueError("invalid atomic setup instructions")
    from solders.instruction import Instruction
    from solders.hash import Hash
    from solders.transaction import Transaction
    from arb.rpc import call
    if any(not isinstance(ix,Instruction) for ix in (*setup,*legs)):
        raise ValueError("all atomic instructions must be verified builders")
    if not hasattr(payer,"pubkey") or not hasattr(payer,"sign_message"):
        raise ValueError("invalid atomic signer")
    recent=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    wire=bytes(Transaction.new_signed_with_payer(
        [*setup,*legs],payer.pubkey(),[payer],Hash.from_string(recent)))
    return {"wire":wire,"hop_count":len(legs),
            "venue_programs":[str(ix.program_id) for ix in legs],
            "local_only":True,"broadcast":False,"simulation_verified":False}
