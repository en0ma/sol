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
    _cpi_intermediate_flow,_top_level_venue_events,LOADER,SAFETY)
from arb.next_ten_fork_pool_probe import PROGRAMS,DECODERS,MINT_KEYS
from arb.next_ten_atomic_routes import BATCH_10
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.pumpswap_local_simulation import local_rpc_only

SYSTEM="11111111111111111111111111111111"

def hydrate(rpc, fixture):
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("isolated Surfpool explicit offline gate required")
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("untrusted source fixture")
    route=(fixture.get("first_venue"),fixture.get("second_venue"))
    if route not in BATCH_10:
        raise ValueError("non-batch ordered pair")
    programs={PROGRAMS[route[0]],PROGRAMS[route[1]]}
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
    for program,(_,elf) in program_data.items():
        for offset in range(0,len(elf),16384):
            call(rpc,"surfnet_writeProgram",[program,elf[offset:offset+16384].hex(),offset])

def build_leg(venue,pool,state,evidence,owner,src,dst,
              mint_in,mint_out,amount,floor):
    if not (type(amount) is int and type(floor) is int and 0<amount<2**64 and 0<floor<2**64):
        raise ValueError("invalid nonzero swap amount")
    if venue=="meteora_damm_v2":
        from arb.meteora_damm_v2_swap import build_swap2
        if (mint_in,mint_out) not in (
            (state["token_a_mint"],state["token_b_mint"]),
            (state["token_b_mint"],state["token_a_mint"])):
            raise ValueError("DAMM pair mismatch")
        return build_swap2(pool,state,owner,src,dst,amount,floor,
                           input_is_a=mint_in==state["token_a_mint"])
    if venue=="raydium_cpmm":
        from arb.raydium_swap import instruction
        if (mint_in,mint_out) not in (
            (state["token_0_mint"],state["token_1_mint"]),
            (state["token_1_mint"],state["token_0_mint"])):
            raise ValueError("CPMM pair mismatch")
        return instruction(pool,state,owner,src,dst,amount,floor,
                           input_is_token_0=mint_in==state["token_0_mint"],
                           expected_mints=None)
    if venue=="orca":
        from arb.whirlpool_swap import build_swap
        from arb.whirlpool_swap import select_tick_arrays
        from arb.whirlpool_preflight import verify_oracle
        a,b=state["token_mint_a"],state["token_mint_b"]
        if (mint_in,mint_out) not in ((a,b),(b,a)):
            raise ValueError("Orca pair mismatch")
        oracle=evidence["oracle"]
        arrays=select_tick_arrays(pool,state["tick_current_index"],
                                  state["tick_spacing"],mint_in==a)
        if not set(arrays).issubset(set(evidence["tick_arrays"])):
            raise ValueError("unauthenticated Orca tick array")
        # Orca accounts are always A/B order, regardless of input direction.
        user_a,user_b=(src,dst) if mint_in==a else (dst,src)
        return build_swap(pool,state,owner,user_a,user_b,oracle,amount,floor,
                          a_to_b=mint_in==a,amount_specified_is_input=True,
                          oracle_writable=state["tick_spacing"]!=state["fee_tier_index_seed"])
    if venue=="meteora_dlmm":
        from arb.meteora_dlmm_swap import build_swap
        x,y=state["token_x_mint"],state["token_y_mint"]
        if (mint_in,mint_out) not in ((x,y),(y,x)):
            raise ValueError("DLMM pair mismatch")
        bins=evidence.get("bin_arrays")
        if not bins or not isinstance(bins,list):
            raise ValueError("authenticated DLMM bins unavailable")
        enriched=dict(state,input_mint=mint_in,output_mint=mint_out)
        return build_swap(pool,enriched,owner,src,dst,state["oracle"],bins,
                          amount,floor,input_is_x=mint_in==x,
                          bitmap_extension=state.get("bitmap_extension"))
    if venue=="pumpswap":
        # PumpSwap buy_v2 is exact OUTPUT, while sell_v2 is exact INPUT.
        # Refuse to use exact-output buy as an exact-input hop without a
        # separately authenticated upper-bound quote and fee PDAs.
        raise ValueError("PumpSwap v2 exact-output / fee-account adapter not yet safe for atomic routing")
    raise ValueError("unsupported execution venue")

def run(rpc,fixture,*,amount_in=100000000,amount_intermediate=1000):
    local_rpc_only(rpc)
    if any(type(n)is not int or not 0<n<2**64 for n in (amount_in,amount_intermediate)):
        raise ValueError("invalid atomic amounts")
    hydrate(rpc,fixture)
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
    ix1=build_leg(first,legs[0][1],states[0],evidence[first],owner,
                  keys[0],keys[1],mints[0],mints[1],amount_in,amount_intermediate)
    ix2=build_leg(second,legs[1][1],states[1],evidence[second],owner,
                  keys[1],keys[2],mints[1],mints[2],amount_intermediate,1)
    bh=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
    tx=Transaction.new_signed_with_payer([ix1,ix2],signer.pubkey(),[signer],bh)
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
    events=_top_level_venue_events(positive.get("logs") or [])
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
    ix2_bad=build_leg(second,legs[1][1],states[1],evidence[second],owner,
                      keys[1],keys[2],mints[1],mints[2],amount_intermediate,2**64-1)
    bad=Transaction.new_signed_with_payer([ix1,ix2_bad],signer.pubkey(),[signer],bh)
    failed,_=_simulate(rpc,bad,keys)
    error=failed.get("err")
    bad_events=_top_level_venue_events(failed.get("logs") or [])
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
    for first,second in BATCH_10:
        name=first+"__"+second+".json"
        out={"status":"MISSING_AUTHENTICATED_SOURCE_FIXTURE",
             "first_venue":first,"second_venue":second,
             "signed_atomic_simulation_verified":False,**SAFETY}
        path=Path(args.fixture_dir)/name
        if path.is_file():
            try:
                out=run("http://127.0.0.1:8899",json.loads(path.read_text()))
            except Exception as exc:
                out.update(status="ISOLATED_SIGNED_ATOMIC_BLOCKED",
                           error_class=type(exc).__name__,diagnostic=str(exc)[:500])
        (root/name).write_text(json.dumps(out,indent=2)+"\n")
        print(json.dumps({"route":name,"status":out["status"],"broadcast":False}))

if __name__=="__main__":
    main()
