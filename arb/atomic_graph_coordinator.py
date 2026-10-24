"""Venue-agnostic atomic graph coordinator and offline transaction packer.

Builds one signed transaction for any connected sequence of venue/pool legs.
All swap-specific details stay in venue_swap_adapter. No sendTransaction.
"""
from arb.venue_swap_adapter import build_leg
from arb.pumpswap_local_simulation import local_rpc_only

MAX_ATOMIC_LEGS=6

def compile_route(legs,tokens,states,evidence,owner,token_accounts,amounts,floors):
    if (not isinstance(legs,list) or not 2<=len(legs)<=MAX_ATOMIC_LEGS
            or not isinstance(tokens,list) or len(tokens)!=len(legs)+1
            or tokens[0]!=tokens[-1]):
        raise ValueError("connected closed token graph with 2–6 legs required")
    if (not isinstance(amounts,(list,tuple)) or not isinstance(floors,(list,tuple))
            or len(amounts)!=len(legs) or len(floors)!=len(legs)):
        raise ValueError("per-leg amount bounds missing")
    if any(type(a) is not int or type(f) is not int or not 0<a<2**64 or not 0<f<2**64
           for a,f in zip(amounts,floors)):
        raise ValueError("invalid per-leg input or minimum output")
    if (not isinstance(owner,str) or not owner
            or any(not isinstance(token,str) for token in tokens)
            or (not isinstance(token_accounts,(list,tuple,dict)))
            or (isinstance(token_accounts,(list,tuple)) and
                (len(token_accounts)!=len(tokens) or any(not isinstance(a,str) or not a for a in token_accounts)))
            or (isinstance(token_accounts,dict) and
                any(token not in token_accounts for token in tokens))):
        raise ValueError("graph token accounts or signer unavailable")
    # Validate the ENTIRE graph before asking any venue builder to encode
    # instructions. An invalid later hop must not partially build earlier hops.
    for i,leg in enumerate(legs):
        if not isinstance(leg,dict):
            raise ValueError("invalid graph edge")
        if leg.get("input_mint")!=tokens[i] or leg.get("output_mint")!=tokens[i+1]:
            raise ValueError("graph edge disconnected")
        key=(leg.get("venue"),leg.get("pool"))
        if key not in states or key not in evidence:
            raise ValueError("authenticated venue state unavailable")
    compiled=[]
    for i,leg in enumerate(legs):
        if not isinstance(leg,dict):
            raise ValueError("invalid graph edge")
        venue,pool=leg["venue"],leg["pool"]
        if leg.get("input_mint")!=tokens[i] or leg.get("output_mint")!=tokens[i+1]:
            raise ValueError("graph edge disconnected")
        if (venue,pool) not in states or (venue,pool) not in evidence:
            raise ValueError("authenticated venue state unavailable")
        # Amounts are set before signing. A later instruction cannot adapt
        # its input by reading the output of an earlier instruction.
        compiled.append(build_leg(
            venue,pool,states[(venue,pool)],evidence[(venue,pool)],owner,
            (token_accounts[i] if not isinstance(token_accounts,dict) else token_accounts[tokens[i]]),
            (token_accounts[i+1] if not isinstance(token_accounts,dict) else token_accounts[tokens[i+1]]),
            tokens[i],tokens[i+1],amounts[i],floors[i]))
    return compiled

def signed_packet(rpc,instructions,signer):
    local_rpc_only(rpc)
    if not 2<=len(instructions)<=MAX_ATOMIC_LEGS:
        raise ValueError("atomic transaction requires 2–6 venue instructions")
    from solders.hash import Hash
    from solders.transaction import Transaction
    from arb.rpc import call
    blockhash=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
    tx=Transaction.new_signed_with_payer(instructions,signer.pubkey(),[signer],blockhash)
    tx.verify()
    if len(bytes(tx))>1232:
        raise ValueError("atomic signed transaction exceeds packet limit")
    return tx

def simulation_decision(*,simulation_verified,rollback_verified,net_profit_base_units=None,
                        live_execution_approved=False):
    # Execution is unavailable during this integration phase, irrespective of
    # quoted profit; live submission is intentionally outside this module.
    return {"simulation_verified":simulation_verified is True,
            "rollback_verified":rollback_verified is True,
            "net_profit_base_units":net_profit_base_units,
            "actionable":False,"live_execution_approved":False,"broadcast":False,
            "decision":"SIMULATION_ONLY"}
