"""Genuinely signed two-instruction isolated Surfpool attempts for ten routes.

Only source-fork authenticated accounts/programs are hydrated; only ephemeral
signer accounts are fabricated. This runner never broadcasts and treats all
failures as unverified. Neither fixtures nor simulation attempts earn credit.
"""
import argparse
import base64
import json
import os
from pathlib import Path
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.transaction import Transaction
from solders.hash import Hash
from arb.rpc import call
from arb.damm_cpmm_atomic_offline import (_pool,_fetch,_simulate,_post,
    _cpi_intermediate_flow,LOADER,SAFETY)
from arb.next_ten_fork_pool_probe import PROGRAMS,DECODERS,MINT_KEYS
from arb.next_ten_atomic_routes import BATCH_10,route_batch
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_local_simulation import local_rpc_only
from arb.atomic_graph_coordinator import compile_route, compile_adaptive_route, signed_packet, simulation_decision

SYSTEM="11111111111111111111111111111111"

def top_level_events(logs, venues):
    import re
    stack=[]
    events=[]
    starts=re.compile(r"^Program (\S+) invoke \[(\d+)\]$")
    ends=re.compile(r"^Program (\S+) (success|failed:.*)$")
    for line in logs:
        if not isinstance(line,str):
            return []
        start=starts.fullmatch(line)
        if start:
            program,depth=start.group(1),int(start.group(2))
            if depth!=len(stack)+1:
                return []
            stack.append(program)
            if depth==1 and program in venues:
                events.append([program,"invoke"])
            continue
        end=ends.fullmatch(line)
        if end:
            if not stack or stack[-1]!=end.group(1):
                return []
            depth=len(stack)
            stack.pop()
            if depth==1 and end.group(1) in venues:
                events.append([end.group(1),"success" if end.group(2)=="success" else "failed"])
    return events if not stack else []

def hydrate(rpc, fixture, *, program_cache=None, batch=BATCH_10):
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("isolated Surfpool explicit offline gate required")
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("untrusted source fixture")
    triangle=fixture.get("fixture_kind") in (
        "THREE_DISTINCT_VENUE_CLOSED_ROUTE",
        "AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE")
    if triangle:
        route=fixture.get("route_venues")
        expected=3 if fixture["fixture_kind"]=="THREE_DISTINCT_VENUE_CLOSED_ROUTE" else None
        if (not isinstance(route,list) or
                (len(route)!=3 and expected==3) or
                (not 4<=len(route)<=6 and expected is None) or
                (len(set(route))!=3 and expected==3) or
                any(v not in PROGRAMS for v in route)):
            raise ValueError("invalid authenticated multihop source fixture")
    else:
        route=(fixture.get("first_venue"),fixture.get("second_venue"))
        if route not in batch:
            raise ValueError("non-batch ordered pair")
    # New contextual fixtures are checked before any hydration/write.
    # Older fixtures remain legacy atomic evidence only, not M5 provenance.
    if "state_account_manifest_sha256" in fixture:
        from arb.source_snapshot_manifest import verify
        verify(fixture)
    programs={PROGRAMS[v] for v in route}
    if "pumpswap" in route:
        from arb.pumpswap_fee_account import PROGRAM as FEE_PROGRAM
        programs.add(FEE_PROGRAM)
    accounts=fixture["accounts"]
    program_data={}
    # Validate every executable + ELF before making any local writes.
    for program in programs:
        info=accounts[program]
        raw=base64.b64decode(info["data"][0],validate=True)
        if info["owner"]!=LOADER or info.get("executable") is not True or raw[:4]!=bytes([2,0,0,0]):
            raise ValueError("invalid captured executable")
        address=str(Pubkey.from_bytes(raw[4:36]))
        pd=accounts[address]
        binary=base64.b64decode(pd["data"][0],validate=True)
        if pd["owner"]!=LOADER or binary[:4]!=bytes([3,0,0,0]) or binary[45:49]!=bytes([127,69,76,70]):
            raise ValueError("invalid authenticated program ELF")
        program_data[program]=(address,binary[45:])
    skip=programs|{v[0] for v in program_data.values()}
    for address,account in accounts.items():
        if address in skip:
            continue
        encoded=account["data"]
        if (not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64"
                or not isinstance(account.get("lamports"),int)):
            raise ValueError("malformed authenticated fork account")
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":account["lamports"],
            "data":base64.b64decode(encoded[0],validate=True).hex(),
            "owner":account["owner"],"executable":account["executable"]}])
    # Source program ELF binaries are immutable within this offline snapshot.
    # Avoid uploading the same multi-megabyte program for every directed pair.
    import hashlib
    for program,(_,elf) in program_data.items():
        digest=hashlib.sha256(elf).hexdigest()
        if program_cache is not None and program_cache.get(program)==digest:
            continue
        for offset in range(0,len(elf),16384):
            call(rpc,"surfnet_writeProgram",[program,elf[offset:offset+16384].hex(),offset])
        if program_cache is not None:
            program_cache[program]=digest


def clmm_direction_evidence(state,mint_in,directional,source_accounts):
    """Select only source-snapshotted tick arrays for the signed mint direction."""
    if mint_in==state["token_mint_0"]:
        key="0_to_1"
    elif mint_in==state["token_mint_1"]:
        key="1_to_0"
    else:
        raise ValueError("CLMM signed input mint mismatches pool")
    arrays=directional.get(key) if isinstance(directional,dict) else None
    if not isinstance(arrays,list) or len(arrays)!=3 or len(set(arrays))!=3:
        raise ValueError("CLMM directional authenticated tick array triplet missing")
    if not isinstance(source_accounts,dict) or any(x not in source_accounts for x in arrays):
        raise ValueError("CLMM directional arrays absent from authenticated source fixture")
    return {"tick_arrays":arrays,"tick_arrays_authenticated":True}

def preflight_first_leg_output(rpc,ix1,signer,keys,mints,owner,before):
    """Plan the final atomic second input from a signed isolated first leg."""
    local_rpc_only(rpc)
    blockhash=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
    tx=Transaction.new_signed_with_payer([ix1],signer.pubkey(),[signer],blockhash)
    tx.verify()
    simulation,_=_simulate(rpc,tx,keys)
    if simulation.get("err") is not None:
        raise ValueError("signed isolated first leg failed: "+str(simulation["err"])[:160])
    accounts=simulation.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=3:
        raise ValueError("standalone signed SPL post accounts missing")
    values=[]
    for i,entry in enumerate(accounts):
        # A standalone first-leg transaction need not load its future
        # terminal token account. Surfpool may return null for that unused
        # address; the separately checked persistent before-snapshot must
        # remain unchanged. Input and intermediate accounts are mandatory.
        if i==2 and entry is None:
            values.append(before[i])
            continue
        if not isinstance(entry,dict) or entry.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("standalone signed SPL owner mismatch")
        raw=entry.get("data")
        if not isinstance(raw,list) or len(raw)!=2 or raw[1]!="base64":
            raise ValueError("standalone signed SPL encoding missing")
        token=decode_token_account(base64.b64decode(raw[0],validate=True))
        if token["mint"]!=mints[i] or token["authority"]!=owner:
            raise ValueError("standalone signed SPL identity mismatch")
        values.append(token["amount_base_units"])
    output=values[1]-before[1]
    if not (type(output)is int and 0<output<2**64 and values[0]<before[0]
            and values[2]==before[2]):
        raise ValueError("standalone signed first-leg SPL output invalid")
    if _post(rpc,keys,mints,owner)!=before:
        raise ValueError("standalone simulation mutated fork balances")
    return {"planned_second_input":output,
            "standalone_compute_units":simulation.get("unitsConsumed"),
            "standalone_signed":True,**SAFETY}

def run(rpc,fixture,*,amount_in=100000000,amount_intermediate=1000,program_cache=None,batch=BATCH_10,
        adaptive_cpmm_v4=False, adaptive_all_venues=False, adaptive_three_hop=False, adaptive_hops=None):
    local_rpc_only(rpc)
    if any(type(n)is not int or not 0<n<2**64 for n in (amount_in,amount_intermediate)):
        raise ValueError("invalid atomic amounts")
    if adaptive_hops is not None:
        if type(adaptive_hops)is not int or not 3<=adaptive_hops<=6:
            raise ValueError("adaptive hops must be 3-6")
        if adaptive_three_hop or adaptive_cpmm_v4 or adaptive_all_venues:
            raise ValueError("select exactly one adaptive execution mode")
    trial_hops=adaptive_hops if adaptive_hops is not None else (3 if adaptive_three_hop else None)
    if trial_hops is not None and {fixture.get("first_venue"),fixture.get("second_venue")}!={"raydium_cpmm","raydium_amm_v4"}:
        raise ValueError("three-hop signed trial needs CPMM/v4 authenticated source")
    if adaptive_three_hop and (adaptive_cpmm_v4 or adaptive_all_venues):
        raise ValueError("three-hop trial independent from two-hop mode")
    if adaptive_cpmm_v4 and adaptive_all_venues:
        raise ValueError("choose one adaptive research mode")
    adaptive_enabled=adaptive_cpmm_v4 or adaptive_all_venues
    if adaptive_cpmm_v4 and {fixture.get("first_venue"),fixture.get("second_venue")}!={"raydium_cpmm","raydium_amm_v4"}:
        raise ValueError("adaptive amount research only supports CPMM and AMM v4")
    hydrate(rpc,fixture,program_cache=program_cache,batch=batch)
    hydration_readback=None
    if "state_account_manifest_sha256" in fixture:
        from arb.hydrated_fork_state_audit import verify_hydrated_state
        hydration_readback=verify_hydrated_state(rpc,fixture)
    first,second=fixture["first_venue"],fixture["second_venue"]
    mints=list(fixture["route_mints"])
    if (len(mints)!=3 or mints[0]!=mints[2] or mints[0]==mints[1]):
        raise ValueError("invalid closed token route")
    if trial_hops is not None:
        mints=[mints[0] if i%2==0 else mints[1] for i in range(trial_hops+1)]
    legs=[(first,fixture["first_pool"]),(second,fixture["second_pool"])]
    states=[]
    for venue,pool in legs:
        state=_pool(rpc,pool,PROGRAMS[venue],DECODERS[venue])
        if set(state[k] for k in MINT_KEYS[venue])!=set(mints[:2]):
            raise ValueError("hydrated pool mints changed")
        states.append(state)
    signer=Keypair()
    owner=str(signer.pubkey())
    keys=[str(Keypair().pubkey()) for _ in range(len(mints))]
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    for i,(key,mint) in enumerate(zip(keys,mints)):
        call(rpc,"surfnet_setAccount",[key,{
            "lamports":2039280,
            "data":token_account_bytes(mint,owner,amount_in if i==0 else 0).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    before=_post(rpc,keys,mints,owner)
    if before!=[amount_in]+[0]*(len(mints)-1):
        raise ValueError("ephemeral funding mismatch")
    evidence=fixture["leg_evidence"]
    if "pumpswap" in (first,second):
        from arb.pumpswap_account_resolver import resolve as resolve_pump
        from arb.pumpswap_pool import verify as verify_pump
        pump_idx=0 if first=="pumpswap" else 1
        pump_state=states[pump_idx]
        pump_pool=legs[pump_idx][1]
        proof=evidence["pumpswap"]
        actual=verify_pump(rpc,pump_pool,pump_state)
        source_verified=proof.get("verified_pool")
        if (not isinstance(source_verified,dict) or
                source_verified.get("address")!=pump_pool or
                source_verified.get("base_mint")!=actual.get("base_mint") or
                source_verified.get("quote_mint")!=actual.get("quote_mint") or
                source_verified.get("global_config")!=actual.get("global_config") or
                source_verified.get("fee_config")!=actual.get("fee_config")):
            raise ValueError("hydrated PumpSwap authentication diverged from source")
        recipient=proof["protocol_fee_recipient"]
        base=pump_state["base_mint"]
        user_base=keys[0 if mints[0]==base else 1]
        user_quote=keys[0 if mints[0]==pump_state["quote_mint"] else 1]
        # Pool may appear on the second leg, whose terminal account is a
        # different SPL address carrying the same starting mint.
        if pump_idx==1:
            user_base=keys[1 if mints[1]==base else 2]
            user_quote=keys[1 if mints[1]==pump_state["quote_mint"] else 2]
        addresses=resolve_pump(actual,owner,user_base,user_quote,recipient)
        from arb.pumpswap_account_metas import account_metas
        direction=("sell" if mints[pump_idx]==base else "buy_exact_quote_in")
        required=account_metas(direction,addresses)["metas"]
        from arb.rpc import call as rpc_call
        for meta in required:
            if meta["name"] in ("user","user_base_token_account",
                                "user_quote_token_account",
                                "system_program","associated_token_program",
                                "base_token_program","quote_token_program",
                                "event_authority","program","fee_program",
                                "coin_creator_vault_authority",
                                "protocol_fee_recipient"):
                continue
            address=meta["address"]
            if address not in fixture["accounts"]:
                raise ValueError("PumpSwap source account not authenticated: "+meta["name"])
        proof["account_addresses"]=addresses
        proof["account_addresses_authenticated"]=True
        buyback=proof.get("buyback_fee_recipient")
        if not isinstance(buyback,str) or buyback not in fixture["accounts"]:
            raise ValueError("PumpSwap V2 authenticated buyback ATA missing")
        addresses["buyback_fee_recipient"]=buyback
        addresses["buyback_fee_recipient_authenticated"]=True
    # Bind source-authenticated CLMM arrays to the actual mint direction.
    # A pool-level union of arrays is not sufficient: the signed builder
    # must receive arrays from the intended exact-input direction only.
    for leg_index,(venue,pool) in enumerate(legs):
        if venue=="raydium_clmm":
            directional=evidence[venue].get("tick_arrays_by_direction")
            evidence[venue].update(clmm_direction_evidence(
                states[leg_index],mints[leg_index],
                directional,fixture["accounts"]))
    graph=[{"venue":first,"pool":legs[0][1],
            "input_mint":mints[0],"output_mint":mints[1]},
           {"venue":second,"pool":legs[1][1],
            "input_mint":mints[1],"output_mint":mints[2]}]
    state_map={(first,legs[0][1]):states[0],(second,legs[1][1]):states[1]}
    proof_map={(first,legs[0][1]):evidence[first],
               (second,legs[1][1]):evidence[second]}
    # Aligned SPL accounts retain distinct input and terminal token accounts
    # even though their mint identities are the same.
    if trial_hops is not None:
        from arb.atomic_graph_coordinator import simulate_adaptive_n_leg_offline
        from arb.venue_swap_adapter import build_leg
        route=[dict(graph[i%2],input_mint=mints[i],output_mint=mints[i+1]) for i in range(trial_hops)]
        def negative(instructions,amounts):
            index=trial_hops-1
            venue,pool=legs[index%2]
            last=build_leg(venue,pool,states[index%2],evidence[venue],owner,
                keys[index],keys[index+1],mints[index],mints[index+1],
                amounts[index],2**64-1)
            return list(instructions[:-1])+[last]
        output=simulate_adaptive_n_leg_offline(
            rpc,route,mints,state_map,proof_map,owner,keys,amount_in,None,
            signer,negative_instructions=negative,require_closed=False)
        output.update(first_venue=first,second_venue=second,
                      route_venues=[legs[i%2][0] for i in range(trial_hops)],
                      route_pool_addresses=[legs[i%2][1] for i in range(trial_hops)],
                      route_mints=mints,source_snapshot_slot=None,
                      execution_environment="ISOLATED_SURFPOOL_OFFLINE",
                      quote_accuracy_verified=False,**SAFETY)
        return output
    adaptive_plan=None
    if adaptive_enabled:
        def observed_first_leg(i,leg,n):
            # Signed standalone observation. The coordinator uses this for
            # the next input; the final leg requires no fabricated observation.
            standalone_first=compile_route(graph,mints,state_map,proof_map,
                owner,keys,[amount_in,amount_intermediate],[1,1])[0]
            measured=preflight_first_leg_output(
                rpc,standalone_first,signer,keys,mints,owner,before)
            return {"signed_offline_observed":measured["standalone_signed"],
                    "output_base_units":measured["planned_second_input"],
                    "compute_units":measured["standalone_compute_units"]}
        assembled=compile_adaptive_route(
            graph,mints,state_map,proof_map,owner,keys,amount_in,observed_first_leg)
        ix1,ix2=assembled["instructions"]
        amount_intermediate=assembled["amounts"][1]
        observation=assembled["observations"][0]
        adaptive_plan={"planned_second_input":amount_intermediate,
                       "standalone_signed":True,
                       "standalone_compute_units":observation.get("compute_units"),
                       "planner_status":assembled["status"]}
    else:
        ix1,ix2=compile_route(graph,mints,state_map,proof_map,owner,keys,
                              [amount_in,amount_intermediate],[amount_intermediate,1])
    from arb.atomic_graph_coordinator import sign_atomic_offline
    tx,lookup,check=sign_atomic_offline(
        rpc,[ix1,ix2],signer,programs=[PROGRAMS[first],PROGRAMS[second]],
        intermediate=keys[1])
    positive,packet=_simulate(rpc,tx,keys)
    result={"status":"POSITIVE_SIGNED_ATOMIC_FAILED" if positive.get("err") else "POSITIVE_PENDING_CPI_CHECK",
            "first_venue":first,"second_venue":second,
            "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
            "signed_transaction_verified":True,
            "transaction_signature":str(tx.signatures[0]),
            "signed_packet_bytes":packet,
            "declared_first_leg_input_base_units":amount_in,
            "declared_second_leg_input_base_units":amount_intermediate,
            "declared_first_leg_minimum_output_base_units":amount_intermediate,
            "declared_second_leg_minimum_output_base_units":1,
            "adaptive_cpmm_v4_amount_planning":adaptive_plan,
            "adaptive_second_input_verified_against_atomic_output":False,
            "route_mints":mints,
            "route_pool_addresses":[legs[0][1],legs[1][1]],
            "source_snapshot_slot":None,  # Fork readback != source mainnet attestation.
            "hydrated_fork_state_readback":hydration_readback,
            "paired_pool_observed_slot":fixture.get("paired_pool_observed_slot"),
            "state_accounts_observed_slot":fixture.get("state_accounts_observed_slot"),
            "state_account_count":fixture.get("state_account_count"),
            "state_account_manifest_sha256":fixture.get("state_account_manifest_sha256"),
            "quote_accuracy_verified":False,
            "positive_logs":positive.get("logs") or [],
            "positive_error":str(positive.get("err")),
            "positive_units_consumed":positive.get("unitsConsumed"),
            "positive_failure_diagnostic":positive.get("err") if positive.get("err") is not None else None,
            "instruction_order_verified":check["instruction_order_verified"],
            "signed_atomic_simulation_verified":False,
            "intermediate_intra_transaction_consumption_verified":False,
            "rollback_failure_case_verified":False,
            "failed_at_second_instruction_after_successful_first":False,
            **SAFETY}
    if positive.get("err") is not None:
        return result
    expected=[[PROGRAMS[first],"invoke"],[PROGRAMS[first],"success"],
              [PROGRAMS[second],"invoke"],[PROGRAMS[second],"success"]]
    events=top_level_events(positive.get("logs") or [],{PROGRAMS[first],PROGRAMS[second]})
    result["positive_top_level_venues"]=[first,second] if events==expected else []
    if events!=expected:
        result["status"]="POSITIVE_PROGRAM_ORDER_NOT_VERIFIED"
        return result
    flow=_cpi_intermediate_flow(tx,positive,keys[1],amount_intermediate,lookup=lookup)
    if flow is None:
        result["status"]="INTERMEDIATE_SPL_CPI_NOT_VERIFIED"
        return result
    posted=positive.get("accounts")
    if not isinstance(posted,list) or len(posted)!=3:
        result["status"]="POSITIVE_SPL_ACCOUNTS_MISSING"
        return result
    amounts=[]
    for i,entry in enumerate(posted):
        if not isinstance(entry,dict) or entry.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("untrusted simulated SPL account")
        token=decode_token_account(base64.b64decode(entry["data"][0],validate=True))
        if token["mint"]!=mints[i] or token["authority"]!=owner:
            raise ValueError("simulated SPL token identity mismatch")
        amounts.append(token["amount_base_units"])
    if not (amounts[0]<before[0] and amounts[2]>0 and
            amounts[1]==flow["first_leg_intermediate_received_base_units"]-amount_intermediate):
        result["status"]="POST_SWAP_BALANCE_RECONCILIATION_FAILED"
        return result
    result["adaptive_second_input_verified_against_atomic_output"]=(
        adaptive_plan is not None and
        flow["first_leg_intermediate_received_base_units"]==amount_intermediate)
    result.update(flow,positive_post_balances_base_units=amounts,
                  initial_balances_base_units=before,
                  signed_intermediate_surplus_base_units=amounts[1],
                  signed_second_leg_consumes_full_first_output=(amounts[1]==0))
    if _post(rpc,keys,mints,owner)!=before:
        raise ValueError("simulation mutated persistent source balances")
    from arb.venue_swap_adapter import build_leg
    ix2_bad=build_leg(second,legs[1][1],states[1],evidence[second],owner,
                      keys[1],keys[2],mints[1],mints[2],amount_intermediate,2**64-1)
    bad,bad_lookup,bad_check=sign_atomic_offline(
        rpc,[ix1,ix2_bad],signer,programs=[PROGRAMS[first],PROGRAMS[second]],
        intermediate=keys[1],lookup=lookup,recent_blockhash=tx.message.recent_blockhash)
    if bad_lookup is not lookup or bad_check["instruction_order_verified"] is not True:
        raise ValueError("negative control changed authenticated transaction account mapping")
    failed,_=_simulate(rpc,bad,keys)
    error=failed.get("err")
    bad_events=top_level_events(failed.get("logs") or [],{PROGRAMS[first],PROGRAMS[second]})
    required=[[PROGRAMS[first],"invoke"],[PROGRAMS[first],"success"],
              [PROGRAMS[second],"invoke"],[PROGRAMS[second],"failed"]]
    failed_index=(error.get("InstructionError",[None])[0]
                  if isinstance(error,dict) else None)
    persistent=_post(rpc,keys,mints,owner)
    rollback=(failed_index==1 and bad_events==required and persistent==before)
    result.update(negative_logs=failed.get("logs") or [],
                  negative_error=str(error),
                  negative_persistent_balances_base_units=persistent,
                  negative_top_level_venues=[first,second] if bad_events==required else [],
                  second_leg_failure_instruction_index=failed_index,
                  failed_at_second_instruction_after_successful_first=rollback,
                  intermediate_intra_transaction_consumption_verified=True,
                  rollback_failure_case_verified=rollback,
                  signed_atomic_simulation_verified=rollback,
                  status="SIGNED_ATOMIC_AND_ROLLBACK_VERIFIED" if rollback
                         else "SECOND_LEG_ATOMIC_ABORT_NOT_VERIFIED")
    return result


def run_three_venue(rpc,fixture,*,amount_in=100_000_000,program_cache=None):
    """Three distinct real source pools through the existing signed N-leg engine."""
    from arb.atomic_graph_coordinator import simulate_adaptive_n_leg_offline
    from arb.venue_swap_adapter import build_leg
    from arb.source_snapshot_manifest import verify
    local_rpc_only(rpc)
    if (fixture.get("fixture_kind")!="THREE_DISTINCT_VENUE_CLOSED_ROUTE" or
            fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL"):
        raise ValueError("authenticated three-venue fixture required")
    verify(fixture)
    venues=fixture.get("route_venues")
    pools=fixture.get("route_pool_addresses")
    mints=fixture.get("route_mints")
    proofs=fixture.get("leg_evidence_by_index")
    if (not all(isinstance(x,list) for x in (venues,pools,mints,proofs))
            or len(venues)!=len(pools)!=len(proofs)!=3 or len(mints)!=4
            or len(set(venues))!=3 or len(set(pools))!=3
            or len(set(mints[:3]))!=3 or mints[-1]!=mints[0]
            or any(v not in PROGRAMS for v in venues)
            or type(amount_in)is not int or not 0<amount_in<2**64):
        raise ValueError("invalid three-venue route topology or amount")
    if any(not isinstance(proof,dict) or proof.get("venue")!=venues[i]
           or proof.get("pool")!=pools[i] for i,proof in enumerate(proofs)):
        raise ValueError("three-venue source leg evidence identity mismatch")
    hydrate(rpc,fixture,program_cache=program_cache)
    from arb.hydrated_fork_state_audit import verify_hydrated_state
    readback=verify_hydrated_state(rpc,fixture)
    states={}
    evidence={}
    route=[]
    for i,(venue,pool) in enumerate(zip(venues,pools)):
        state=_pool(rpc,pool,PROGRAMS[venue],DECODERS[venue])
        if set(state[k] for k in MINT_KEYS[venue])!={mints[i],mints[i+1]}:
            raise ValueError("hydrated third-venue pool mint identity changed")
        proof=dict(proofs[i])
        if venue=="raydium_clmm":
            proof.update(clmm_direction_evidence(
                state,mints[i],proof.get("tick_arrays_by_direction"),fixture["accounts"]))
        if venue=="pumpswap":
            raise ValueError("three-venue PumpSwap requires source account resolver integration")
        states[(venue,pool)]=state
        evidence[(venue,pool)]=proof
        route.append({"venue":venue,"pool":pool,
                      "input_mint":mints[i],"output_mint":mints[i+1]})
    signer=Keypair()
    owner=str(signer.pubkey())
    keys=[str(Keypair().pubkey()) for _ in mints]
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1_000_000_000,
        "data":"","owner":SYSTEM,"executable":False}])
    for i,(key,mint) in enumerate(zip(keys,mints)):
        call(rpc,"surfnet_setAccount",[key,{"lamports":2_039_280,
            "data":token_account_bytes(mint,owner,amount_in if i==0 else 0).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    if _post(rpc,keys,mints,owner)!=[amount_in,0,0,0]:
        raise ValueError("three-venue ephemeral SPL initial snapshot mismatch")
    def negative(instructions,amounts):
        ix=build_leg(venues[-1],pools[-1],states[(venues[-1],pools[-1])],
                     evidence[(venues[-1],pools[-1])],owner,
                     keys[-2],keys[-1],mints[-2],mints[-1],
                     amounts[-1],2**64-1)
        return list(instructions[:-1])+[ix]
    receipt=simulate_adaptive_n_leg_offline(
        rpc,route,mints,states,evidence,owner,keys,amount_in,None,signer,
        negative_instructions=negative,require_closed=True)
    receipt.update(route_venues=venues,route_pool_addresses=pools,route_mints=mints,
        fixture_kind=fixture["fixture_kind"],
        source_snapshot_slot=None,
        state_accounts_observed_slot=fixture["state_accounts_observed_slot"],
        state_account_manifest_sha256=fixture["state_account_manifest_sha256"],
        hydrated_fork_state_readback=readback,
        execution_environment="ISOLATED_SURFPOOL_OFFLINE",
        independently_validated_quote_samples=0,**SAFETY)
    return receipt


def run_four_to_six_venue(rpc,fixture,*,amount_in=100_000,program_cache=None):
    """Actually hydrate, construct, sign and simulate an authenticated 4–6-hop route.

    Reuse the existing 2–6-hop adaptive signer and independent CPI/rollback
    verifier. The result is experimental and never authorizes broadcasting.
    An unsupported venue builder returns a concrete failure receipt.
    """
    from arb.atomic_graph_coordinator import simulate_adaptive_n_leg_offline
    from arb.venue_swap_adapter import build_leg
    from arb.source_snapshot_manifest import verify
    local_rpc_only(rpc)
    if (fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE"
            or fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL"
            or any(fixture.get(k) is not False for k in SAFETY)):
        raise ValueError("safe authenticated four-to-six-hop source fixture required")
    verify(fixture)
    venues=fixture.get("route_venues")
    pools=fixture.get("route_pool_addresses")
    mints=fixture.get("route_mints")
    proofs=fixture.get("leg_evidence_by_index")
    if (not isinstance(venues,list) or not isinstance(pools,list)
            or not isinstance(mints,list) or not isinstance(proofs,list)
            or not 4<=len(venues)<=6 or len(pools)!=len(venues)
            or len(proofs)!=len(venues) or len(mints)!=len(venues)+1
            or len(set(pools))!=len(pools) or mints[0]!=mints[-1]
            or any(v not in PROGRAMS for v in venues)
            or type(amount_in)is not int or not 0<amount_in<2**64):
        raise ValueError("invalid four-to-six-hop source route topology")
    if any(not isinstance(proof,dict) or proof.get("venue")!=venues[i]
           or proof.get("pool")!=pools[i] for i,proof in enumerate(proofs)):
        raise ValueError("four-to-six-hop source evidence identity mismatch")
    # Hydration reuses the same full verified source inventory as the accepted
    # three-leg runner. Only temporary user accounts and signer are synthetic.
    hydrate(rpc,fixture,program_cache=program_cache)
    from arb.hydrated_fork_state_audit import verify_hydrated_state
    readback=verify_hydrated_state(rpc,fixture)
    states={}
    evidence={}
    route=[]
    for i,(venue,pool) in enumerate(zip(venues,pools)):
        state=_pool(rpc,pool,PROGRAMS[venue],DECODERS[venue])
        if set(state[k] for k in MINT_KEYS[venue])!={mints[i],mints[i+1]}:
            raise ValueError("hydrated four-to-six-hop pool mint changed")
        proof=dict(proofs[i])
        # Four-hop source capture wraps venue_accounts evidence inside
        # "auxiliary"; flatten only the authenticated source-derived fields.
        aux=proof.pop("auxiliary",None)
        if not isinstance(aux,dict):
            raise ValueError("four-to-six-hop source venue builder evidence missing")
        proof.update(aux)
        if venue=="raydium_clmm":
            proof.update(clmm_direction_evidence(
                state,mints[i],proof.get("tick_arrays_by_direction"),fixture["accounts"]))
        states[(venue,pool)]=state
        evidence[(venue,pool)]=proof
        route.append({"venue":venue,"pool":pool,
                      "input_mint":mints[i],"output_mint":mints[i+1]})
    signer=Keypair()
    owner=str(signer.pubkey())
    keys=[str(Keypair().pubkey()) for _ in mints]
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1_000_000_000,
        "data":"","owner":SYSTEM,"executable":False}])
    for i,(key,mint) in enumerate(zip(keys,mints)):
        call(rpc,"surfnet_setAccount",[key,{"lamports":2_039_280,
            "data":token_account_bytes(mint,owner,amount_in if i==0 else 0).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    before=_post(rpc,keys,mints,owner)
    if before!=[amount_in]+[0]*len(venues):
        raise ValueError("four-to-six-hop source user token initialization inconsistent")
    def negative(instructions,amounts):
        last=len(venues)-1
        bad=build_leg(venues[last],pools[last],states[(venues[last],pools[last])],
            evidence[(venues[last],pools[last])],owner,
            keys[-2],keys[-1],mints[-2],mints[-1],amounts[-1],2**64-1)
        return list(instructions[:-1])+[bad]
    receipt=simulate_adaptive_n_leg_offline(
        rpc,route,mints,states,evidence,owner,keys,amount_in,None,signer,
        negative_instructions=negative,require_closed=True)
    receipt.update(route_venues=venues,route_pool_addresses=pools,route_mints=mints,
        fixture_kind=fixture["fixture_kind"],
        source_snapshot_slot=None,
        state_accounts_observed_slot=fixture["state_accounts_observed_slot"],
        state_account_manifest_sha256=fixture["state_account_manifest_sha256"],
        hydrated_fork_state_readback=readback,
        execution_environment="ISOLATED_SURFPOOL_OFFLINE",
        independently_validated_quote_samples=0,**SAFETY)
    if receipt.get("positive_post_balances_base_units") is not None:
        from arb.m5_signed_start_mint_economics import signed_net_economics
        receipt["signed_start_mint_economics"]=signed_net_economics(
            receipt,start_mint=mints[0],
            source_slot=fixture["state_accounts_observed_slot"])
    return receipt

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture-dir")
    p.add_argument("--three-venue-fixture")
    p.add_argument("--four-to-six-venue-fixture")
    p.add_argument("--output-dir",required=True)
    p.add_argument("--batch",choices=("first","next","remaining","non-v4"),default="first")
    p.add_argument("--shard-index",type=int,default=0)
    p.add_argument("--shard-count",type=int,default=1)
    p.add_argument("--only-venue",choices=("raydium_amm_v4",))
    p.add_argument("--adaptive-cpmm-v4",action="store_true")
    p.add_argument("--adaptive-all-venues",action="store_true")
    p.add_argument("--adaptive-three-hop",action="store_true")
    p.add_argument("--adaptive-hops",type=int,choices=(3,4,5,6))
    p.add_argument("--only-cpmm-v4",action="store_true")
    args=p.parse_args()
    local_rpc_only("http://127.0.0.1:8899")
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=True)
    if args.four_to_six_venue_fixture:
        path=Path(args.four_to_six_venue_fixture)
        out={"status":"FOUR_TO_SIX_SIGNED_EXECUTION_BLOCKED",
             "signed_atomic_simulation_verified":False,**SAFETY}
        (root/"four-to-six-venue.json").write_text(json.dumps(out,indent=2)+"\n")
        try:
            out=run_four_to_six_venue("http://127.0.0.1:8899",
                                     json.loads(path.read_text()),program_cache={})
        except Exception as exc:
            out.update(error_class=type(exc).__name__,diagnostic=str(exc)[:500])
        (root/"four-to-six-venue.json").write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps({"route":"four-to-six-venues","status":out["status"],
                          "broadcast":False}),flush=True)
        return
    if args.three_venue_fixture:
        path=Path(args.three_venue_fixture)
        result={"status":"THREE_VENUE_SIGNED_EXECUTION_BLOCKED",**SAFETY}
        (root/"three-venue.json").write_text(json.dumps(result,indent=2)+"\n")
        try:
            result=run_three_venue("http://127.0.0.1:8899",
                                   json.loads(path.read_text()),program_cache={})
        except Exception as exc:
            result.update(error_class=type(exc).__name__,diagnostic=str(exc)[:500])
        (root/"three-venue.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"route":"three-distinct-venues","status":result["status"],
                          "broadcast":False}),flush=True)
        return
    if not args.fixture_dir:
        p.error("--fixture-dir required for pair trials")
    if not 1<=args.shard_count<=42 or not 0<=args.shard_index<args.shard_count:
        raise ValueError("invalid deterministic offline work shard")
    program_cache={}
    for index,(first,second) in enumerate(route_batch(args.batch)):
        if args.only_venue and args.only_venue not in (first,second):
            continue
        if args.only_cpmm_v4 and {first,second}!={"raydium_cpmm","raydium_amm_v4"}:
            continue
        if index%args.shard_count!=args.shard_index:
            continue
        name=first+"__"+second+".json"
        out={"status":"MISSING_AUTHENTICATED_SOURCE_FIXTURE",
             "first_venue":first,"second_venue":second,
             "signed_atomic_simulation_verified":False,**SAFETY}
        path=Path(args.fixture_dir)/name
        # Write a durable per-route receipt BEFORE any heavy local ELF
        # hydration; interrupted CI must not lose all diagnostic evidence.
        (root/name).write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps({"route":name,"status":"ATTEMPT_STARTED","broadcast":False}),flush=True)
        if path.is_file():
            try:
                out=run("http://127.0.0.1:8899",json.loads(path.read_text()),
                        program_cache=program_cache,batch=route_batch(args.batch),
                        adaptive_cpmm_v4=args.adaptive_cpmm_v4,
                        adaptive_all_venues=args.adaptive_all_venues,
                        adaptive_three_hop=args.adaptive_three_hop,
                        adaptive_hops=args.adaptive_hops)
            except Exception as exc:
                out.update(status="ISOLATED_SIGNED_ATOMIC_BLOCKED",
                           error_class=type(exc).__name__,diagnostic=str(exc)[:500])
        (root/name).write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps({"route":name,"status":out["status"],"broadcast":False}),flush=True)

if __name__=="__main__":
    main()
