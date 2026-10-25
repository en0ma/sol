"""Venue-agnostic atomic graph coordinator and offline transaction packer.

Builds one signed transaction for any connected sequence of venue/pool legs.
All swap-specific details stay in venue_swap_adapter. No sendTransaction.
"""
from arb.venue_swap_adapter import build_leg
from arb.pumpswap_local_simulation import local_rpc_only

MAX_ATOMIC_LEGS=6

def compile_route(legs,tokens,states,evidence,owner,token_accounts,amounts,floors,*,require_closed=True):
    if (not isinstance(legs,list) or not 2<=len(legs)<=MAX_ATOMIC_LEGS
            or not isinstance(tokens,list) or len(tokens)!=len(legs)+1
            or (require_closed and tokens[0]!=tokens[-1])):
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

def compile_adaptive_route(legs,tokens,states,evidence,owner,token_accounts,
                           initial_amount,observe,*,floors=None,require_closed=True):
    """Reuse signed-observation planner and existing seven-venue builder."""
    from arb.adaptive_route_amount_planner import plan
    if (not isinstance(legs,list) or not isinstance(tokens,list)
            or len(tokens)!=len(legs)+1
            or any(not isinstance(leg,dict) or leg.get("input_mint")!=tokens[i]
                   or leg.get("output_mint")!=tokens[i+1]
                   for i,leg in enumerate(legs))):
        raise ValueError("invalid adaptive token connectivity")
    planned=plan(legs,initial_amount,observe,require_closed=require_closed)
    minimums=[1]*len(legs) if floors is None else floors
    instructions=compile_route(legs,tokens,states,evidence,owner,token_accounts,
                               planned["amounts"],minimums,require_closed=require_closed)
    return {"status":"ADAPTIVE_INSTRUCTIONS_COMPILED_NOT_EXECUTION_VERIFIED",
            "amounts":planned["amounts"],"observations":planned["observations"],
            "instructions":instructions,"atomic_execution_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

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
        raise ValueError(f"atomic signed transaction exceeds packet limit: {len(bytes(tx))} > 1232 bytes; requires authenticated v0 address lookup table support")
    return tx

def sign_atomic_offline(rpc,instructions,signer,*,programs,intermediate,lookup=None,recent_blockhash=None):
    """Sign and independently preflight any two-leg graph, legacy first, v0 if oversized.

    No DEX-name special cases. Offline ALT provisioning is only permitted when
    an oversized legacy packet needs compression; negative controls reuse
    the same lookup table rather than creating a different transaction context.
    """
    from solders.hash import Hash
    from solders.transaction import Transaction
    from arb.rpc import call
    from arb.signed_atomic_instruction_preflight import inspect_signed_legacy_order
    from arb.atomic_v0_lookup import sign_v0_offline,verify_v0_order,sign_v0_with_lookup
    local_rpc_only(rpc)
    if len(instructions)!=2 or len(programs)!=2 or programs[0]==programs[1]:
        raise ValueError("expected exactly two distinct ordered swap venues")
    blockhash=recent_blockhash or Hash.from_string(call(
        rpc,"getLatestBlockhash")["value"]["blockhash"])
    if lookup is not None:
        tx=sign_v0_with_lookup(instructions,signer,blockhash,lookup)
        check=verify_v0_order(tx,lookup,programs[0],programs[1],intermediate)
        return tx,lookup,check
    legacy=Transaction.new_signed_with_payer(
        instructions,signer.pubkey(),[signer],blockhash)
    legacy.verify()
    if len(bytes(legacy))<=1232:
        check=inspect_signed_legacy_order(
            bytes(legacy),programs[0],programs[1],
            intermediate_account=intermediate)
        return legacy,None,check
    tx,lookup=sign_v0_offline(rpc,instructions,signer,blockhash)
    check=verify_v0_order(tx,lookup,programs[0],programs[1],intermediate)
    return tx,lookup,check

def audit_n_leg_balances(amounts, before, after, *, rollback_balances=None, later_instruction_failed=False):
    """Check actual signed N-leg SPL balances, never inferred preflight output."""
    n=len(amounts) if isinstance(amounts,(list,tuple)) else 0
    if not 2<=n<=MAX_ATOMIC_LEGS or not isinstance(before,(list,tuple)) or not isinstance(after,(list,tuple)) or len(before)!=n+1 or len(after)!=n+1:
        raise ValueError("2-6 hop signed balance inventory required")
    if any(type(x)is not int or not 0<=x<2**64 for x in list(before)+list(after)+list(amounts)) or any(x<=0 for x in amounts):
        raise ValueError("invalid signed SPL amount")
    failures=[]
    if before[0]-after[0]!=amounts[0]:
        failures.append("initial signed exact input mismatch")
    for i in range(1,n):
        if before[i]!=after[i]:
            failures.append("intermediate residual at hop "+str(i))
    if after[-1]<=before[-1]:
        failures.append("positive terminal output missing")
    if rollback_balances is None or list(rollback_balances)!=list(before):
        failures.append("negative persistent rollback unmatched")
    if later_instruction_failed is not True:
        failures.append("negative later instruction failure not proved")
    return {"status":"N_LEG_BALANCES_AND_ROLLBACK_RECONCILED" if not failures else "UNVERIFIED",
            "legs":n,"failure_reasons":failures,
            "signed_cpi_per_leg_verified":False,
            "source_rpc_independently_attested":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def simulation_decision(*,simulation_verified,rollback_verified,net_profit_base_units=None,
                        live_execution_approved=False):
    # Execution is unavailable during this integration phase, irrespective of
    # quoted profit; live submission is intentionally outside this module.
    return {"simulation_verified":simulation_verified is True,
            "rollback_verified":rollback_verified is True,
            "net_profit_base_units":net_profit_base_units,
            "actionable":False,"live_execution_approved":False,"broadcast":False,
            "decision":"SIMULATION_ONLY"}
