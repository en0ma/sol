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

def sign_adaptive_n_leg_offline(rpc,instructions,signer,*,programs,intermediates):
    """Sign 2–6 ordered venue swaps using existing legacy/v0 packers.

    Validates venue program order and adjacent intermediate-account sharing
    without requiring distinct venue identities. Does not simulate, attest
    CPI token amounts, establish price parity, or authorize submission.
    """
    from solders.hash import Hash
    from solders.transaction import Transaction
    from solders.pubkey import Pubkey
    from arb.rpc import call
    from arb.atomic_v0_lookup import sign_v0_offline,resolved_v0_keys
    local_rpc_only(rpc)
    n=len(instructions) if isinstance(instructions,(list,tuple)) else 0
    if not 2<=n<=MAX_ATOMIC_LEGS or len(programs)!=n or len(intermediates)!=n-1:
        raise ValueError("2-6 instructions and N-1 intermediate SPL accounts required")
    if any(not isinstance(p,str) or not p for p in programs):
        raise ValueError("expected venue program identities")
    blockhash=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
    tx=Transaction.new_signed_with_payer(instructions,signer.pubkey(),[signer],blockhash)
    tx.verify()
    lookup=None
    if len(bytes(tx))>1232:
        tx,lookup=sign_v0_offline(rpc,instructions,signer,blockhash)
        keys=resolved_v0_keys(tx.message,lookup)
    else:
        keys=list(tx.message.account_keys)
    compiled=tx.message.instructions
    if len(compiled)!=n:
        raise ValueError("signed instruction count mismatch")
    actual=[str(keys[i.program_id_index]) for i in compiled]
    if actual!=list(programs):
        raise ValueError("signed N-leg venue ordering mismatch")
    for i,account in enumerate(intermediates):
        mid=Pubkey.from_string(account)
        if mid not in keys:
            raise ValueError("intermediate SPL account missing at hop "+str(i+1))
        key_index=keys.index(mid)
        if key_index not in compiled[i].accounts or key_index not in compiled[i+1].accounts:
            raise ValueError("intermediate SPL account not linked across hops "+str(i+1))
    return tx,lookup,{"instruction_order_verified":True,
                      "intermediate_account_linkage_verified":True,
                      "legs":n,"actionable":False,
                      "live_execution_approved":False,"broadcast":False}

def audit_n_leg_cpi(tx,response,accounts,amounts,*,lookup=None):
    """Independently reconcile each intermediate SPL transfer from signed CPI.

    Reuses the existing SPL transfer decoder and loaded v0 keys. A final
    balance-only check cannot prove an intermediate was produced and consumed.
    """
    from solders.pubkey import Pubkey
    from arb.damm_cpmm_atomic_offline import _inner_token_transfer
    from arb.token_vaults import TOKEN_PROGRAM
    if not isinstance(accounts,(list,tuple)) or not isinstance(amounts,(list,tuple)):
        raise ValueError("missing atomic SPL account or amount inventory")
    n=len(amounts)
    if not 2<=n<=MAX_ATOMIC_LEGS or len(accounts)!=n+1 or len(set(accounts))!=n+1:
        raise ValueError("distinct per-boundary SPL accounts required")
    if any(type(a)is not int or not 0<a<2**64 for a in amounts):
        raise ValueError("invalid exact input amounts")
    keys=(list(tx.message.account_keys) if lookup is None else
          __import__("arb.atomic_v0_lookup",fromlist=["resolved_v0_keys"]).resolved_v0_keys(tx.message,lookup))
    token=Pubkey.from_string(TOKEN_PROGRAM)
    token_index=keys.index(token) if token in keys else None
    rows=response.get("innerInstructions") if isinstance(response,dict) else None
    if not isinstance(rows,list):
        raise ValueError("signed inner SPL instructions unavailable")
    groups={}
    for entry in rows:
        if not isinstance(entry,dict) or type(entry.get("index")) is not int:
            raise ValueError("invalid inner instruction group")
        index=entry["index"]
        if index<0 or index>=n or index in groups or not isinstance(entry.get("instructions"),list):
            raise ValueError("ambiguous inner instruction group")
        groups[index]=entry["instructions"]
    if len(groups)!=n:
        raise ValueError("signed leg CPI groups incomplete")
    hops=[]
    for i in range(1,n):
        account=accounts[i]
        received=consumed=0
        for outer in (i-1,i):
            for instruction in groups[outer]:
                flow=_inner_token_transfer(instruction,keys,token_index)
                if flow is None:
                    continue
                src,dst,quantity=flow
                if outer==i-1 and dst==account:
                    received+=quantity
                if outer==i and src==account:
                    consumed+=quantity
        if received!=amounts[i] or consumed!=amounts[i]:
            raise ValueError("signed CPI full intermediate consumption mismatch hop "+str(i))
        hops.append({"hop":i,"account":account,
                     "received_base_units":received,"consumed_base_units":consumed,
                     "planned_input_base_units":amounts[i]})
    return {"status":"N_LEG_SIGNED_CPI_RECONCILED","hops":hops,
            "signed_cpi_per_leg_verified":True,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

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

MAX_SOLANA_COMPUTE_UNITS=1_400_000

def verify_signed_compute_budget(simulated, *, stage):
    """Fail closed on missing or over-limit signed simulation compute evidence."""
    consumed=simulated.get("unitsConsumed") if isinstance(simulated,dict) else None
    if type(consumed)is not int or not 0<consumed<=MAX_SOLANA_COMPUTE_UNITS:
        raise ValueError("invalid signed "+stage+" compute units")
    return consumed

def verify_signed_prefix_balances(simulated, tokens, owner, initial_amount,
                                  planned_inputs, prefix_index):
    """Verify all touched SPL accounts after a signed cumulative prefix.

    Untouched future accounts may be null because Solana RPC need not load
    accounts absent from the signed message. Every touched account is required.
    """
    import base64
    from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
    n=len(tokens)-1
    rows=simulated.get("accounts") if isinstance(simulated,dict) else None
    if (not isinstance(rows,list) or len(rows)!=len(tokens)
            or not 0<=prefix_index<n or len(planned_inputs)!=prefix_index+1
            or any(type(x)is not int or not 0<x<2**64 for x in planned_inputs)):
        raise ValueError("invalid signed prefix evidence inventory")
    values=[]
    for index,row in enumerate(rows[:prefix_index+2]):
        if not isinstance(row,dict) or row.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("signed prefix touched SPL account absent")
        data=row.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("signed prefix touched SPL encoding absent")
        token=decode_token_account(base64.b64decode(data[0],validate=True))
        if token["mint"]!=tokens[index] or token["authority"]!=owner:
            raise ValueError("signed prefix touched SPL identity mismatch")
        value=token["amount_base_units"]
        if type(value)is not int or not 0<=value<2**64:
            raise ValueError("signed prefix touched SPL amount invalid")
        values.append(value)
    if values[0]!=initial_amount-planned_inputs[0]:
        raise ValueError("signed prefix initial debit mismatch")
    if any(value!=0 for value in values[1:-1]):
        raise ValueError("signed prefix prior intermediate residual")
    if values[-1]<=0:
        raise ValueError("signed prefix terminal output missing")
    return values[-1]

def signed_prefix_observer(rpc,legs,tokens,states,evidence,owner,accounts,signer,
                           *,initial_amount):
    """Build and signed-simulate each growing route prefix to observe next input.

    Never treat a quote as an observed amount. Every prefix is simulated on
    the same unchanged disposable fork; previous legs are included so pool
    price impact and account state are replayed for the observed output.
    One intermediate SPL output account is mandatory in the RPC response.
    """
    import base64
    from solders.hash import Hash
    from solders.transaction import Transaction
    from arb.rpc import call
    from arb.damm_cpmm_atomic_offline import _simulate,_post
    from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
    from arb.atomic_v0_lookup import sign_v0_offline
    local_rpc_only(rpc)
    n=len(legs)
    if (not 2<=n<=6 or len(tokens)!=n+1 or len(accounts)!=n+1
            or len(set(accounts))!=n+1):
        raise ValueError("invalid adaptive prefix account inventory")
    initial=_post(rpc,accounts,tokens,owner)
    if initial!=[initial_amount]+[0]*n:
        raise ValueError("signed prefix initial SPL state mismatch")
    prefix=[]
    planned_inputs=[]
    last_index=-1
    def observe(i,leg,amount):
        nonlocal last_index
        if i!=last_index+1 or i>=n-1 or leg!=legs[i]:
            raise ValueError("signed prefix observer out of sequence")
        # Do not advance the observer or retain an instruction until the
        # entire signed prefix has succeeded, including SPL reconciliation.
        ix=build_leg(leg["venue"],leg["pool"],
            states[(leg["venue"],leg["pool"])],
            evidence[(leg["venue"],leg["pool"])],owner,
            accounts[i],accounts[i+1],tokens[i],tokens[i+1],amount,1)
        candidate=prefix+[ix]
        blockhash=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
        tx=Transaction.new_signed_with_payer(candidate,signer.pubkey(),[signer],blockhash)
        tx.verify()
        if len(bytes(tx))>1232:
            if len(candidate)==1:
                raise ValueError("single-leg signed prefix exceeds packet limit")
            tx,_=sign_v0_offline(rpc,candidate,signer,blockhash)
        simulated,_=_simulate(rpc,tx,accounts)
        if simulated.get("err") is not None:
            raise ValueError("signed prefix simulation failed: "+str(simulated["err"])[:160])
        units=verify_signed_compute_budget(simulated,stage="prefix")
        output=verify_signed_prefix_balances(
            simulated,tokens,owner,initial_amount,planned_inputs+[amount],i)
        if _post(rpc,accounts,tokens,owner)!=initial:
            raise ValueError("signed prefix mutated persistent token state")
        prefix.append(ix)
        planned_inputs.append(amount)
        last_index=i
        return {"signed_offline_observed":True,"output_base_units":output,
                "compute_units":units}
    return observe

def signed_n_leg_post_balances(simulation, accounts, mints, authority):
    """Decode all returned user token accounts, never infer zero leftovers."""
    import base64
    from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
    rows=simulation.get("accounts") if isinstance(simulation,dict) else None
    if not isinstance(rows,list) or len(rows)!=len(accounts) or len(rows)!=len(mints):
        raise ValueError("signed positive N-leg token account inventory missing")
    balances=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict) or row.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("signed SPL owner mismatch at index "+str(i))
        data=row.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("invalid signed SPL encoding")
        token=decode_token_account(base64.b64decode(data[0],validate=True))
        if token["mint"]!=mints[i] or token["authority"]!=authority:
            raise ValueError("signed SPL mint/authority mismatch at index "+str(i))
        balances.append(token["amount_base_units"])
    return balances

def simulate_adaptive_n_leg_offline(rpc, legs, tokens, states, evidence, owner,
                                    accounts, initial_amount, observe, signer,
                                    *, negative_instructions=None, require_closed=True):
    """Execute signed offline 2–6-leg adaptive route with CPI and rollback gates.

    The supplied observer must independently sign/simulate prefix legs on the
    disposable fork. No broadcast is available. A negative-control builder
    must break the final swap while preserving all earlier instructions.
    """
    from arb.damm_cpmm_atomic_offline import _simulate, _post
    from arb.next_ten_signed_atomic_offline import top_level_events
    from arb.next_ten_fork_pool_probe import PROGRAMS
    local_rpc_only(rpc)
    n=len(legs)
    if not 2<=n<=6 or len(accounts)!=n+1 or len(set(accounts))!=n+1:
        raise ValueError("2-6 legs and distinct N+1 user token accounts required")
    before=_post(rpc,accounts,tokens,owner)
    if before!=[initial_amount]+[0]*n:
        raise ValueError("untrusted initial user SPL balance inventory")
    if observe is None:
        observe=signed_prefix_observer(rpc,legs,tokens,states,evidence,owner,
                                       accounts,signer,initial_amount=initial_amount)
    planned=compile_adaptive_route(legs,tokens,states,evidence,owner,accounts,
                                   initial_amount,observe,require_closed=require_closed)
    programs=[PROGRAMS[leg["venue"]] for leg in legs]
    tx,lookup,order=sign_adaptive_n_leg_offline(
        rpc,planned["instructions"],signer,programs=programs,intermediates=accounts[1:-1])
    from arb.m5_signed_message_fee_estimate import estimate_signed_message_fee
    estimate=estimate_signed_message_fee(rpc,tx)
    positive,packet=_simulate(rpc,tx,accounts)
    import hashlib
    import base64
    signed_digest=hashlib.sha256(bytes(tx)).hexdigest()
    signed_signature=str(tx.signatures[0])
    receipt={"status":"UNVERIFIED","legs":n,"planned_inputs":planned["amounts"],
             "signed_prefix_observations":planned.get("observations",[]),
             "initial_balances_base_units":list(before),
             "signed_packet_bytes":packet,
             "signed_transaction_sha256":signed_digest,
             "signed_transaction_wire_base64":base64.b64encode(bytes(tx)).decode("ascii"),
             "signed_transaction_signature":signed_signature,
             "signed_packet_crypto_bound":True,
             "positive_error":str(positive.get("err")),
             "signed_message_fee_estimate":estimate,
             "signed_cpi_per_leg_verified":False,"rollback_failure_case_verified":False,
             "signed_atomic_simulation_verified":False,"quote_accuracy_verified":False,
             "actionable":False,"live_execution_approved":False,"broadcast":False}
    if positive.get("err") is not None:
        return receipt
    try:
        receipt["positive_units_consumed"]=verify_signed_compute_budget(
            positive,stage="atomic")
    except ValueError as exc:
        receipt["status"]="SIGNED_COMPUTE_BUDGET_UNVERIFIED"
        receipt["reason"]=str(exc)
        return receipt
    expected=[event for p in programs for event in ([p,"invoke"],[p,"success"])]
    if top_level_events(positive.get("logs") or [],set(programs))!=expected:
        receipt["status"]="POSITIVE_ORDER_UNVERIFIED"
        return receipt
    try:
        flow=audit_n_leg_cpi(tx,positive,accounts,planned["amounts"],lookup=lookup)
    except ValueError as exc:
        receipt["status"]="CPI_CONTINUITY_UNVERIFIED"
        receipt["reason"]=str(exc)[:160]
        return receipt
    receipt["cpi_hops"]=flow["hops"]
    receipt["signed_cpi_per_leg_verified"]=True
    try:
        posted=signed_n_leg_post_balances(positive,accounts,tokens,owner)
    except ValueError as exc:
        receipt["status"]="SIGNED_POST_BALANCES_UNVERIFIED"
        receipt["reason"]=str(exc)[:160]
        return receipt
    receipt["positive_post_balances_base_units"]=posted
    # Check signed positive input/output movement and zero residual before
    # treating the later negative rollback control as useful evidence.
    if posted[0]!=before[0]-planned["amounts"][0] or any(
            posted[i]!=before[i] for i in range(1,n)) or posted[-1]<=before[-1]:
        receipt["status"]="SIGNED_POST_BALANCE_CONTINUITY_FAILED"
        return receipt
    if _post(rpc,accounts,tokens,owner)!=before:
        raise ValueError("positive simulation mutated persistent fork accounts")
    if negative_instructions is None:
        receipt["status"]="NEGATIVE_CONTROL_MISSING"
        return receipt
    bad_ix=negative_instructions(planned["instructions"],planned["amounts"])
    if not isinstance(bad_ix,(tuple,list)) or len(bad_ix)!=n:
        raise ValueError("negative instruction list malformed")
    if any(bytes(a)!=bytes(b) for a,b in zip(planned["instructions"][:-1],bad_ix[:-1])):
        raise ValueError("negative control modified earlier swap instructions")
    from solders.transaction import Transaction
    from arb.atomic_v0_lookup import sign_v0_with_lookup
    blockhash=tx.message.recent_blockhash
    if lookup is None:
        bad_tx=Transaction.new_signed_with_payer(bad_ix,signer.pubkey(),[signer],blockhash)
        bad_tx.verify()
    else:
        bad_tx=sign_v0_with_lookup(bad_ix,signer,blockhash,lookup)
    failure,bad_packet=_simulate(rpc,bad_tx,accounts)
    negative_digest=hashlib.sha256(bytes(bad_tx)).hexdigest()
    if signed_digest==negative_digest or signed_signature==str(bad_tx.signatures[0]):
        raise ValueError("negative control did not cryptographically change transaction")
    error=failure.get("err")
    idx=error.get("InstructionError",[None])[0] if isinstance(error,dict) else None
    fail_expected=[event for p in programs[:-1] for event in ([p,"invoke"],[p,"success"])]
    fail_expected.extend(([programs[-1],"invoke"],[programs[-1],"failed"]))
    rollback=(idx==n-1 and top_level_events(failure.get("logs") or [],set(programs))==fail_expected
              and _post(rpc,accounts,tokens,owner)==before)
    receipt.update(negative_error=str(error),negative_failure_instruction_index=idx,negative_packet_bytes=bad_packet,
                   negative_signed_transaction_sha256=negative_digest,
                   negative_signed_transaction_wire_base64=base64.b64encode(bytes(bad_tx)).decode("ascii"),
                   negative_signed_transaction_signature=str(bad_tx.signatures[0]),
                   rollback_failure_case_verified=rollback,
                   signed_atomic_simulation_verified=rollback,
                   status="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED" if rollback else "ROLLBACK_UNVERIFIED")
    return receipt

def simulation_decision(*,simulation_verified,rollback_verified,net_profit_base_units=None,
                        live_execution_approved=False):
    # Execution is unavailable during this integration phase, irrespective of
    # quoted profit; live submission is intentionally outside this module.
    return {"simulation_verified":simulation_verified is True,
            "rollback_verified":rollback_verified is True,
            "net_profit_base_units":net_profit_base_units,
            "actionable":False,"live_execution_approved":False,"broadcast":False,
            "decision":"SIMULATION_ONLY"}


def coordinate_registered_cycle_offline(rpc,registry,route,states,evidence,owner,
                                        token_accounts,initial_amount,signer,
                                        *,negative_instructions,observe=None):
    """Run an admitted registered 2-6-leg cycle through the EXISTING coordinator.

    The registered pool list is authoritative for identity; venue builders
    still enforce their already-authenticated state/evidence requirements.
    Price amounts come from signed adaptive prefix observations, not invented
    coordinator spot quotes. No network broadcasting is exposed.
    """
    from arb.next_ten_fork_pool_probe import PROGRAMS
    local_rpc_only(rpc)
    supported={"orca","raydium_cpmm","meteora_damm_v2",
               "pumpswap","meteora_dlmm","raydium_clmm"}
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
        or not isinstance(route,dict) or not isinstance(route.get("legs"),list)
        or not 2<=len(route["legs"])<=MAX_ATOMIC_LEGS
        or type(initial_amount)is not int or not 0<initial_amount<2**64
        or negative_instructions is None):
        raise ValueError("registered 2-6 leg coordinator inputs required")
    registered={}
    for pool in registry["pools"]:
        if not isinstance(pool,dict):
            raise ValueError("malformed admitted registry identity")
        key=(pool.get("venue"),pool.get("address"))
        if key in registered:
            raise ValueError("duplicate admitted registry identity")
        registered[key]=pool
    legs=[]
    tokens=[]
    used=set()
    for i,row in enumerate(route["legs"]):
        if not isinstance(row,dict):
            raise ValueError("malformed registered route leg")
        venue,pool=row.get("venue"),row.get("pool")
        key=(venue,pool)
        start=row.get("input_mint",row.get("input"))
        end=row.get("output_mint",row.get("output"))
        if (venue not in supported or venue not in PROGRAMS or
            key not in registered or key in used or
            not isinstance(start,str) or not start or
            not isinstance(end,str) or not end or start==end):
            raise ValueError("route contains unsupported, duplicate or unregistered pool")
        recorded=registered[key].get("mints")
        if recorded is not None and (not isinstance(recorded,list)
                                     or len(recorded)!=2 or set(recorded)!={start,end}):
            raise ValueError("registered pool mint identity mismatch")
        if key not in states or key not in evidence:
            raise ValueError("registered pool authenticated builder state unavailable")
        if i and tokens[-1]!=start:
            raise ValueError("registered route token path disconnected")
        if not tokens:
            tokens.append(start)
        tokens.append(end)
        used.add(key)
        legs.append({"venue":venue,"pool":pool,
                     "input_mint":start,"output_mint":end})
    if tokens[0]!=tokens[-1] or (
        isinstance(route.get("start_mint"),str) and
        route["start_mint"]!=tokens[0]):
        raise ValueError("registered arbitrage route must close at start mint")
    if (not isinstance(token_accounts,(list,tuple)) or
        len(token_accounts)!=len(tokens) or
        len(set(token_accounts))!=len(token_accounts) or
        any(not isinstance(a,str) or not a for a in token_accounts)):
        raise ValueError("distinct per-hop signed user SPL accounts required")
    # The existing signer, adaptive prefix simulator, venue instruction
    # adapter, CPI verifier and rollback verifier remain authoritative.
    receipt=simulate_adaptive_n_leg_offline(
        rpc,legs,tokens,states,evidence,owner,list(token_accounts),
        initial_amount,observe,signer,negative_instructions=negative_instructions)
    return {"status":"REGISTERED_SIX_VENUE_COORDINATOR_OFFLINE_RESULT",
            "route_legs":len(legs),"route_venues":[r["venue"] for r in legs],
            "signed_receipt":receipt,
            "signed_atomic_simulation_verified":
                receipt.get("signed_atomic_simulation_verified") is True,
            "coordinator_live_eligible":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}


def registered_cycles_for_coordinator(registry, *, max_cycles=200):
    """Enumerate actual 2-6-hop candidates using already-admitted pool identities.

    This calls the existing opportunity graph, not a replacement discovery,
    authentication, pricing or registry implementation. Unsupported seventh
    venues and incomplete legacy mint hints are simply not graph edges.
    """
    from arb.opportunity_graph import cycles
    supported={"orca","raydium_cpmm","meteora_damm_v2",
               "pumpswap","meteora_dlmm","raydium_clmm"}
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
        or len(registry["pools"])>200 or
        type(max_cycles)is not int or not 1<=max_cycles<=500):
        raise ValueError("bounded already-admitted pool registry required")
    ready=[]
    seen=set()
    for row in registry["pools"]:
        if not isinstance(row,dict):
            raise ValueError("malformed coordinator registry row")
        venue,pool=row.get("venue"),row.get("address")
        if venue not in supported:
            continue
        key=(venue,pool)
        if key in seen:
            raise ValueError("duplicate coordinator registry identity")
        seen.add(key)
        mints=row.get("mints")
        if mints is None:
            continue
        if (not isinstance(mints,list) or len(mints)!=2 or
            any(not isinstance(m,str) or not m for m in mints) or
            mints[0]==mints[1] or not isinstance(pool,str) or not pool):
            raise ValueError("invalid admitted pool mint pair")
        ready.append({"venue":venue,"address":pool,
                      "mints":mints,"verified":True})
    generated=cycles(ready,max_hops=6,min_hops=2,
                     max_cycles=max_cycles+1,truncate=True) if ready else []
    return {"status":"REGISTERED_SIX_VENUE_CYCLE_CANDIDATES",
            "routes":[{"start_mint":r["start_mint"],"hops":r["hops"],
                       "legs":r["legs"],"signed_simulation_verified":False}
                      for r in generated[:max_cycles]],
            "candidate_count":min(max_cycles,len(generated)),
            "truncated":len(generated)>max_cycles,
            "actionable":False,"live_execution_approved":False,"broadcast":False}


def run_registered_cycle_batch_offline(rpc,registry,prepared,*,max_cycles=12):
    """Bounded registry -> existing graph -> signed coordinator dispatch.

    prepared is indexed by the exact canonical (venue,pool,input,output)
    sequence. Each entry supplies signer, local initial SPL accounts, signed
    negative-control builder and already authenticated builder states.
    No fabricated instruction inputs, implicit signer, price refresh or send.
    Different candidate failures remain individually visible.
    """
    local_rpc_only(rpc)
    if (not isinstance(prepared,dict) or type(max_cycles)is not int
        or not 1<=max_cycles<=50):
        raise ValueError("bounded explicit coordinator preparation required")
    inventory=registered_cycles_for_coordinator(registry,max_cycles=max_cycles)
    rows=[]
    for index,candidate in enumerate(inventory["routes"]):
        legs=candidate["legs"]
        identity=tuple((leg["venue"],leg["pool"],leg["input"],leg["output"])
                       for leg in legs)
        config=prepared.get(identity)
        if config is None:
            rows.append({"index":index,"status":"NOT_PREPARED_FOR_SIGNED_EXECUTION",
                         "legs":len(legs),"signed_atomic_simulation_verified":False})
            continue
        if not isinstance(config,dict):
            rows.append({"index":index,"status":"MALFORMED_SIGNED_ROUTE_PREPARATION",
                         "legs":len(legs),"signed_atomic_simulation_verified":False})
            continue
        required=("states","evidence","owner","token_accounts",
                  "initial_amount","signer","negative_instructions")
        if any(key not in config for key in required):
            rows.append({"index":index,"status":"MISSING_SIGNED_ROUTE_PREPARATION",
                         "legs":len(legs),"signed_atomic_simulation_verified":False})
            continue
        try:
            receipt=coordinate_registered_cycle_offline(
                rpc,registry,candidate,config["states"],config["evidence"],
                config["owner"],config["token_accounts"],
                config["initial_amount"],config["signer"],
                negative_instructions=config["negative_instructions"],
                observe=config.get("observe"))
        except (ValueError,KeyError,TypeError) as exc:
            rows.append({"index":index,"status":"SIGNED_COORDINATOR_ROUTE_REJECTED",
                         "legs":len(legs),"reason":str(exc)[:200],
                         "signed_atomic_simulation_verified":False})
            continue
        rows.append({"index":index,"status":receipt["signed_receipt"].get("status","UNVERIFIED"),
                     "legs":len(legs),
                     "signed_atomic_simulation_verified":
                         receipt["signed_atomic_simulation_verified"],
                     "signed_receipt":receipt["signed_receipt"]})
    return {"status":"REGISTERED_SIX_VENUE_SIGNED_BATCH_OFFLINE_ONLY",
            "candidate_count":inventory["candidate_count"],
            "inventory_truncated":inventory["truncated"],
            "prepared_routes":sum(row["status"] not in
                ("NOT_PREPARED_FOR_SIGNED_EXECUTION","MALFORMED_SIGNED_ROUTE_PREPARATION",
                 "MISSING_SIGNED_ROUTE_PREPARATION") for row in rows),
            "signed_atomic_verified_routes":sum(
                row["signed_atomic_simulation_verified"] for row in rows),
            "routes":rows,"actionable":False,
            "live_execution_approved":False,"broadcast":False}


def rank_registered_cycle_candidates(registry,initial_amount,quote_leg,*,max_cycles=200):
    """Amount-aware route ordering using EXISTING per-venue native price callback.

    quote_leg(venue,pool,input_mint,output_mint,amount_in) must return an
    authenticated exact-output integer, or a row with output_base_units,
    source_slot and source_verified=True. It must not return a float.
    This is prioritization only: signing and CPI/SPL checks remain mandatory.
    """
    if (type(initial_amount)is not int or not 0<initial_amount<2**64
        or not callable(quote_leg)):
        raise ValueError("exact input and existing venue quote callback required")
    candidates=registered_cycles_for_coordinator(registry,max_cycles=max_cycles)
    ranked=[]
    blocked=[]
    for index,route in enumerate(candidates["routes"]):
        current=initial_amount
        observed=[]
        try:
            for leg in route["legs"]:
                raw=quote_leg(leg["venue"],leg["pool"],
                              leg["input"],leg["output"],current)
                if isinstance(raw,dict):
                    if raw.get("source_verified") is not True or (
                        type(raw.get("source_slot")) is not int or
                        raw["source_slot"]<0):
                        raise ValueError("source-bound native quote evidence missing")
                    output=raw.get("output_base_units")
                    slot=raw["source_slot"]
                else:
                    # Bare integer quotes cannot prove which pool state was
                    # used. They remain unusable for coordinator ranking.
                    raise ValueError("source-bound native quote evidence missing")
                if type(output)is not int or not 0<output<2**64:
                    raise ValueError("invalid native quote raw output")
                observed.append({"venue":leg["venue"],"pool":leg["pool"],
                                 "input_base_units":current,
                                 "output_base_units":output,
                                 "source_slot":slot})
                current=output
        except (ValueError,KeyError,TypeError) as exc:
            blocked.append({"index":index,"reason":str(exc)[:160]})
            continue
        ranked.append({"index":index,"route":route,
                       "start_mint":route["start_mint"],"start_amount_base_units":initial_amount,
                       "final_amount_base_units":current,
                       "gross_delta_base_units":current-initial_amount,
                       "quoted_legs":observed,
                       "signed_simulation_verified":False})
    ranked.sort(key=lambda x:(-x["gross_delta_base_units"],x["index"]))
    return {"status":"REGISTERED_CYCLE_NATIVE_QUOTE_RANKING_ONLY",
            "ranked":ranked,"blocked":blocked,
            "candidate_count":candidates["candidate_count"],
            "gross_positive_candidates":sum(x["gross_delta_base_units"]>0 for x in ranked),
            "net_profitability_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}


def coordinate_ranked_registered_cycles_offline(rpc,registry,initial_amount,
                                                quote_leg,prepared,*,max_cycles=12):
    """Run existing venue quotes -> ranked registered routes -> signed atomics.

    The quote callback uses each venue's ALREADY-IMPLEMENTED native price.
    Offline preparations must be supplied explicitly for exact user SPL
    accounts, signer and negative control; no synthetic admission occurs.
    Signed receipts, not indicative gross quotes, determine verification.
    """
    local_rpc_only(rpc)
    if not isinstance(prepared,dict) or type(max_cycles)is not int or not 1<=max_cycles<=50:
        raise ValueError("bounded signed ranked coordinator preparation required")
    ranking=rank_registered_cycle_candidates(
        registry,initial_amount,quote_leg,max_cycles=max_cycles)
    attempts=[]
    for item in ranking["ranked"]:
        route=item["route"]
        identity=tuple((leg["venue"],leg["pool"],leg["input"],leg["output"])
                       for leg in route["legs"])
        config=prepared.get(identity)
        if not isinstance(config,dict):
            attempts.append({"index":item["index"],
                             "status":"NOT_PREPARED_FOR_SIGNED_EXECUTION",
                             "signed_atomic_simulation_verified":False})
            continue
        required=("states","evidence","owner","token_accounts",
                  "signer","negative_instructions")
        if any(k not in config for k in required):
            attempts.append({"index":item["index"],
                             "status":"MISSING_SIGNED_ROUTE_PREPARATION",
                             "signed_atomic_simulation_verified":False})
            continue
        try:
            result=coordinate_registered_cycle_offline(
                rpc,registry,route,config["states"],config["evidence"],
                config["owner"],config["token_accounts"],initial_amount,
                config["signer"],
                negative_instructions=config["negative_instructions"],
                observe=config.get("observe"))
            receipt=result["signed_receipt"]
            attempts.append({"index":item["index"],
                             "status":receipt.get("status","UNVERIFIED"),
                             "signed_atomic_simulation_verified":
                                 result["signed_atomic_simulation_verified"],
                             "signed_receipt":receipt})
        except (ValueError,KeyError,TypeError) as exc:
            attempts.append({"index":item["index"],
                             "status":"SIGNED_COORDINATOR_ROUTE_REJECTED",
                             "reason":str(exc)[:200],
                             "signed_atomic_simulation_verified":False})
    return {"status":"REGISTERED_NATIVE_RANKED_SIGNED_COORDINATOR_OFFLINE",
            "candidate_count":ranking["candidate_count"],
            "price_quoted_candidates":len(ranking["ranked"]),
            "price_blocked_candidates":len(ranking["blocked"]),
            "ranked_attempts":attempts,
            "signed_atomic_verified_routes":sum(
                x["signed_atomic_simulation_verified"] for x in attempts),
            "net_profitability_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
