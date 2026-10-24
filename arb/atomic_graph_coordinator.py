"""Venue-agnostic atomic graph coordinator and offline transaction packer.

Builds one signed transaction for any connected sequence of venue/pool legs.
All swap-specific details stay in venue_swap_adapter. No sendTransaction.
"""
from arb.venue_swap_adapter import build_leg
from arb.pumpswap_local_simulation import local_rpc_only

def compile_route(legs,tokens,states,evidence,owner,token_accounts,amounts,floors):
    if (not isinstance(legs,list) or not 2<=len(legs)<=3
            or not isinstance(tokens,list) or len(tokens)!=len(legs)+1
            or tokens[0]!=tokens[-1] or len(set(tokens[:-1]))!=len(tokens)-1):
        raise ValueError("connected two/three-leg closed token graph required")
    if len(amounts)!=len(legs) or len(floors)!=len(legs):
        raise ValueError("per-leg amount bounds missing")
    if (not isinstance(owner,str) or not owner
            or any(not isinstance(token,str) or token not in token_accounts for token in tokens)):
        raise ValueError("graph token accounts or signer unavailable")
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
            token_accounts[tokens[i]],token_accounts[tokens[i+1]],
            tokens[i],tokens[i+1],amounts[i],floors[i]))
    return compiled

def signed_packet(rpc,instructions,signer):
    local_rpc_only(rpc)
    if not 2<=len(instructions)<=3:
        raise ValueError("atomic transaction must contain 2 or 3 swap instructions")
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
