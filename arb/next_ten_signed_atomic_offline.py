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
from arb.next_ten_atomic_routes import BATCH_10
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_local_simulation import local_rpc_only
from arb.atomic_graph_coordinator import compile_route, signed_packet, simulation_decision

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

def hydrate(rpc, fixture, *, program_cache=None):
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("isolated Surfpool explicit offline gate required")
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("untrusted source fixture")
    route=(fixture.get("first_venue"),fixture.get("second_venue"))
    if route not in BATCH_10:
        raise ValueError("non-batch ordered pair")
    programs={PROGRAMS[route[0]],PROGRAMS[route[1]]}
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


def run(rpc,fixture,*,amount_in=100000000,amount_intermediate=1000,program_cache=None):
    local_rpc_only(rpc)
    if any(type(n)is not int or not 0<n<2**64 for n in (amount_in,amount_intermediate)):
        raise ValueError("invalid atomic amounts")
    hydrate(rpc,fixture,program_cache=program_cache)
    first,second=fixture["first_venue"],fixture["second_venue"]
    mints=fixture["route_mints"]
    if (len(mints)!=3 or mints[0]!=mints[2] or mints[0]==mints[1]):
        raise ValueError("invalid closed token route")
    legs=[(first,fixture["first_pool"]),(second,fixture["second_pool"])]
    states=[]
    for venue,pool in legs:
        state=_pool(rpc,pool,PROGRAMS[venue],DECODERS[venue])
        if set(state[k] for k in MINT_KEYS[venue])!=set(mints[:2]):
            raise ValueError("hydrated pool mints changed")
        states.append(state)
    signer=Keypair()
    owner=str(signer.pubkey())
    keys=[str(Keypair().pubkey()) for _ in range(3)]
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    for i,(key,mint) in enumerate(zip(keys,mints)):
        call(rpc,"surfnet_setAccount",[key,{
            "lamports":2039280,
            "data":token_account_bytes(mint,owner,amount_in if i==0 else 0).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    before=_post(rpc,keys,mints,owner)
    if before!=[amount_in,0,0]:
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
    graph=[{"venue":first,"pool":legs[0][1],
            "input_mint":mints[0],"output_mint":mints[1]},
           {"venue":second,"pool":legs[1][1],
            "input_mint":mints[1],"output_mint":mints[2]}]
    state_map={(first,legs[0][1]):states[0],(second,legs[1][1]):states[1]}
    proof_map={(first,legs[0][1]):evidence[first],
               (second,legs[1][1]):evidence[second]}
    # Aligned SPL accounts retain distinct input and terminal token accounts
    # even though their mint identities are the same.
    ix1,ix2=compile_route(graph,mints,state_map,proof_map,owner,keys,
                          [amount_in,amount_intermediate],[amount_intermediate,1])
    tx=signed_packet(rpc,[ix1,ix2],signer)
    tx.verify()
    # Solana signed two-instruction preflight checks account continuity.
    from arb.signed_atomic_instruction_preflight import inspect_signed_legacy_order
    check=inspect_signed_legacy_order(bytes(tx),PROGRAMS[first],PROGRAMS[second],
                                      intermediate_account=keys[1])
    positive,packet=_simulate(rpc,tx,keys)
    result={"status":"POSITIVE_SIGNED_ATOMIC_FAILED" if positive.get("err") else "POSITIVE_PENDING_CPI_CHECK",
            "first_venue":first,"second_venue":second,
            "execution_environment":"ISOLATED_SURFPOOL_OFFLINE",
            "signed_transaction_verified":True,
            "transaction_signature":str(tx.signatures[0]),
            "signed_packet_bytes":packet,
            "route_mints":mints,
            "positive_logs":positive.get("logs") or [],
            "positive_error":str(positive.get("err")),
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
    flow=_cpi_intermediate_flow(tx,positive,keys[1],amount_intermediate)
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
    result.update(flow,positive_post_balances_base_units=amounts,
                  initial_balances_base_units=before)
    if _post(rpc,keys,mints,owner)!=before:
        raise ValueError("simulation mutated persistent source balances")
    from arb.venue_swap_adapter import build_leg
    ix2_bad=build_leg(second,legs[1][1],states[1],evidence[second],owner,
                      keys[1],keys[2],mints[1],mints[2],amount_intermediate,2**64-1)
    bad=Transaction.new_signed_with_payer([ix1,ix2_bad],signer.pubkey(),[signer],tx.message.recent_blockhash)
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

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture-dir",required=True)
    p.add_argument("--output-dir",required=True)
    args=p.parse_args()
    local_rpc_only("http://127.0.0.1:8899")
    root=Path(args.output_dir)
    root.mkdir(parents=True,exist_ok=True)
    program_cache={}
    for first,second in BATCH_10:
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
                        program_cache=program_cache)
            except Exception as exc:
                out.update(status="ISOLATED_SIGNED_ATOMIC_BLOCKED",
                           error_class=type(exc).__name__,diagnostic=str(exc)[:500])
        (root/name).write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps({"route":name,"status":out["status"],"broadcast":False}),flush=True)

if __name__=="__main__":
    main()
