"""Signed DAMM-v2 -> Raydium CPMM atomic local-fork integration.

Both programs and pools must be genuine authenticated fork snapshots; only
ephemeral user accounts are locally fabricated. No sendTransaction/broadcast.
The route WSOL -> USDC -> WSOL is an allowed closed case (not a requirement).
"""
import argparse
import base64
import json
import os
from pathlib import Path
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.damm_v2_fork_execution import _account_snapshot, SAFETY
from arb.meteora_damm_v2 import PROGRAM as DAMM, decode as decode_damm, verify as verify_damm
from arb.damm_v2_signed_preflight import authenticate_pool
from arb.meteora_damm_v2_swap import build_swap2
from arb.raydium_cpmm import PROGRAM as CPMM, decode as decode_cpmm, verify_vaults
from arb.raydium_swap import instruction as cpmm_instruction
from arb.token_vaults import TOKEN_PROGRAM
from arb.orca_swap_v2_offline_provision import token_account_bytes

DAMM_POOL="8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie"
CPMM_POOL="7JuwJuNU88gurFnyWeiyGKbFmExMWcmRZntn9imEzdny"
LOADER="BPFLoaderUpgradeab1e11111111111111111111111"


def _pool(rpc, address, program, decoder):
    response=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
    account=response.get("value") if isinstance(response,dict) else None
    if not isinstance(account,dict) or account.get("owner")!=program or account.get("executable") is not False:
        raise ValueError("authenticated venue pool unavailable: "+address)
    data=account.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("pool account encoding invalid")
    return decoder(base64.b64decode(data[0],validate=True))


def _fetch(rpc, addresses):
    response=call(rpc,"getMultipleAccounts",[
        addresses,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value") if isinstance(response,dict) else None
    if not isinstance(values,list) or len(values)!=len(addresses) or any(not isinstance(v,dict) for v in values):
        raise ValueError("missing authenticated fork account")
    return dict(zip(addresses,values))


def export(rpc, output, *, damm_pool=DAMM_POOL, cpmm_pool=CPMM_POOL):
    """Read-only fixture export; MUST run before upstream-backed fork is stopped."""
    local_rpc_only(rpc)
    damm=_pool(rpc,damm_pool,DAMM,decode_damm)
    proof=verify_damm(rpc,damm_pool,damm)
    if proof.get("venue")!="meteora_damm_v2" or proof.get("address")!=damm_pool:
        raise ValueError("DAMM pool authentication missing")
    cpmm=_pool(rpc,cpmm_pool,CPMM,decode_cpmm)
    cpmm_proof=verify_vaults(rpc,cpmm_pool,cpmm,expected_mints=None)
    if cpmm_proof.get("verified") is not True:
        raise ValueError("CPMM vault authentication missing")
    mint_x=damm["token_a_mint"]
    mint_y=damm["token_b_mint"]
    if mint_y not in (cpmm["token_0_mint"],cpmm["token_1_mint"]):
        raise ValueError("two authenticated pools do not share intermediate mint")
    mint_z=(cpmm["token_1_mint"] if cpmm["token_0_mint"]==mint_y
            else cpmm["token_0_mint"])
    if mint_z!=mint_x or mint_x==mint_y:
        raise ValueError("pinned route is not WSOL -> USDC -> WSOL")
    if any(cpmm[k]!=TOKEN_PROGRAM for k in ("token_0_program","token_1_program")):
        raise ValueError("CPMM token program unsupported")
    addresses=list(dict.fromkeys([
        damm_pool,damm["token_a_vault"],damm["token_b_vault"],
        damm["token_a_mint"],damm["token_b_mint"],
        cpmm_pool,cpmm["token_0_vault"],cpmm["token_1_vault"],
        cpmm["amm_config"],cpmm["observation"],CPMM,DAMM]))
    accounts=_fetch(rpc,addresses)
    from solders.pubkey import Pubkey
    for program in (DAMM,CPMM):
        entry=accounts[program]
        raw=base64.b64decode(entry["data"][0],validate=True)
        if entry.get("owner")!=LOADER or entry.get("executable") is not True or raw[:4]!=bytes([2,0,0,0]):
            raise ValueError("authenticated executable program unavailable")
        pd=str(Pubkey.from_bytes(raw[4:36]))
        accounts.update(_fetch(rpc,[pd]))
        pd_account=accounts[pd]
        pd_raw=base64.b64decode(pd_account["data"][0],validate=True)
        if pd_account.get("owner")!=LOADER or pd_raw[:4]!=bytes([3,0,0,0]) or pd_raw[45:49]!=bytes([127,69,76,70]):
            raise ValueError("authenticated program ELF unavailable")
    payload={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
             "venue_pair":["meteora_damm_v2","raydium_cpmm"],
             "damm_pool":damm_pool,"cpmm_pool":cpmm_pool,
             "mints":[mint_x,mint_y,mint_z],"accounts":accounts,
             "damm_slot":proof["slot"],"cpmm_slot":cpmm_proof["slot"],
             "signed_atomic_simulation_verified":False,**SAFETY}
    Path(output).write_text(json.dumps(payload))
    return {"status":"AUTHENTICATED_ATOMIC_FIXTURE_EXPORTED",
            "accounts":len(accounts),**SAFETY}


def _hydrate(rpc, fixture):
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or fixture.get("venue_pair")!=["meteora_damm_v2","raydium_cpmm"]:
        raise ValueError("untrusted atomic fixture")
    accounts=fixture["accounts"]
    programdatas={}
    from solders.pubkey import Pubkey
    # Verify program-data integrity before ANY local writes.
    for program in (DAMM,CPMM):
        info=accounts[program]
        raw=base64.b64decode(info["data"][0],validate=True)
        if info.get("owner")!=LOADER or info.get("executable") is not True or raw[:4]!=bytes([2,0,0,0]):
            raise ValueError("unsupported captured executable")
        addr=str(Pubkey.from_bytes(raw[4:36]))
        pd=accounts[addr]
        elf=base64.b64decode(pd["data"][0],validate=True)
        if pd.get("owner")!=LOADER or elf[:4]!=bytes([3,0,0,0]) or elf[45:49]!=bytes([127,69,76,70]):
            raise ValueError("invalid captured programdata")
        programdatas[program]=(addr,elf[45:])
    ignored={*programdatas}
    ignored.update(x[0] for x in programdatas.values())
    for address,account in accounts.items():
        if address in ignored:
            continue
        encoded=account["data"]
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("invalid fixture account encoding")
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":account["lamports"],
            "data":base64.b64decode(encoded[0],validate=True).hex(),
            "owner":account["owner"],"executable":account["executable"]}])
    for program,(_,elf) in programdatas.items():
        for offset in range(0,len(elf),16384):
            call(rpc,"surfnet_writeProgram",[program,elf[offset:offset+16384].hex(),offset])


def _simulate(rpc, tx, addresses):
    tx.verify()
    wire=bytes(tx)
    if len(wire)>1232:
        raise ValueError("signed two-venue transaction exceeds Solana packet size")
    response=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode(),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "innerInstructions":True,
         "accounts":{"encoding":"base64","addresses":addresses}}])
    value=response.get("value") if isinstance(response,dict) else None
    if not isinstance(value,dict):
        raise ValueError("missing signed atomic simulation response")
    return value,len(wire)


def _post(rpc, accounts, mints, owner):
    _,bal=_account_snapshot(rpc,accounts,mints,owner)
    return bal


def _cpi_intermediate_flow(tx, response, intermediate):
    """Require real inner token transfers into Y from leg 1 and out in leg 2."""
    from solders.pubkey import Pubkey
    keys=tx.message.account_keys
    index=keys.index(Pubkey.from_string(intermediate))
    token_index=keys.index(Pubkey.from_string(TOKEN_PROGRAM))
    rows=response.get("innerInstructions")
    if not isinstance(rows,list):
        return False
    proven=[]
    for index_outer in (0,1):
        group=next((g for g in rows if g.get("index")==index_outer),None)
        if not isinstance(group,dict):
            return False
        found=False
        for entry in group.get("instructions",[]):
            if (entry.get("programIdIndex")!=token_index
                    or not isinstance(entry.get("accounts"),list)):
                continue
            accounts=entry["accounts"]
            # SPL Token Transfer/TransferChecked: source account is first,
            # destination is second (for both opcodes).
            if len(accounts)<2:
                continue
            if index_outer==0 and accounts[1]==index:
                found=True
            if index_outer==1 and accounts[0]==index:
                found=True
        proven.append(found)
    return proven==[True,True]


def run(rpc, fixture, *, first_input=100000000, second_input=1000, second_floor=1):
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("atomic execution requires explicitly isolated offline Surfpool")
    if any(type(v)is not int or not 0<v<1<<64 for v in (first_input,second_input,second_floor)):
        raise ValueError("positive atomic trade amounts required")
    _hydrate(rpc,fixture)
    damm_pool,cpmm_pool=fixture["damm_pool"],fixture["cpmm_pool"]
    damm=_pool(rpc,damm_pool,DAMM,decode_damm)
    proof=verify_damm(rpc,damm_pool,damm)
    auth=authenticate_pool(rpc,damm_pool,damm,proof)
    if auth.get("pool_reauthenticated") is not True:
        raise ValueError("DAMM reauthentication failed")
    cpmm=_pool(rpc,cpmm_pool,CPMM,decode_cpmm)
    verified=verify_vaults(rpc,cpmm_pool,cpmm,expected_mints=None)
    if verified.get("verified") is not True:
        raise ValueError("CPMM reauthentication failed")
    mint_x,mint_y,mint_z=fixture["mints"]
    if ((damm["token_a_mint"],damm["token_b_mint"])!=(mint_x,mint_y)
            or mint_y not in (cpmm["token_0_mint"],cpmm["token_1_mint"])
            or mint_z!=(cpmm["token_1_mint"] if cpmm["token_0_mint"]==mint_y else cpmm["token_0_mint"])):
        raise ValueError("atomic pool route changed since source authentication")
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    payer=Keypair()
    owner=str(payer.pubkey())
    keys=[str(Keypair().pubkey()) for _ in range(3)]
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
        "data":"","owner":"11111111111111111111111111111111","executable":False}])
    for address,mint,amount in zip(keys,(mint_x,mint_y,mint_z),(first_input,0,0)):
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,
            "data":token_account_bytes(mint,owner,amount).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    before=_post(rpc,keys,(mint_x,mint_y,mint_z),owner)
    if before!=[first_input,0,0]:
        raise ValueError("ephemeral user token balances incorrect")
    ix1=build_swap2(damm_pool,damm,owner,keys[0],keys[1],
                    first_input,second_input,input_is_a=True)
    # Exactly consume a bounded subset of the first leg's independently
    # verified minimum output, so Y is actually produced then consumed.
    cpmm_direction=cpmm["token_0_mint"]==mint_y
    ix2=cpmm_instruction(cpmm_pool,cpmm,owner,keys[1],keys[2],
                         second_input,second_floor,
                         input_is_token_0=cpmm_direction,
                         expected_mints=None)
    bh=Hash.from_string(call(rpc,"getLatestBlockhash")["value"]["blockhash"])
    tx=Transaction.new_signed_with_payer([ix1,ix2],payer.pubkey(),[payer],bh)
    from arb.signed_atomic_instruction_preflight import inspect_signed_legacy_order
    structure=inspect_signed_legacy_order(bytes(tx),DAMM,CPMM,
                                           intermediate_account=keys[1])
    positive,packet=_simulate(rpc,tx,keys)
    report={"status":"ATOMIC_EXECUTION_NOT_VERIFIED",
            "damm_pool":damm_pool,"cpmm_pool":cpmm_pool,
            "mints":[mint_x,mint_y,mint_z],
            "signed_packet_bytes":packet,
            "signature":str(tx.signatures[0]),
            "positive_error":str(positive.get("err")),
            "positive_logs":positive.get("logs",[]),
            "first_leg_output_floor":second_input,
            "second_leg_input_base_units":second_input,
            "instruction_order_verified":structure["instruction_order_verified"],
            "signed_atomic_simulation_verified":False,
            "rollback_failure_case_verified":False,
            "intermediate_intra_transaction_consumption_verified":False,
            **SAFETY}
    if positive.get("err") is not None:
        report["status"]="POSITIVE_ATOMIC_SIMULATION_FAILED"
        return report
    logs=positive.get("logs") or []
    events=[]
    for line in logs:
        for program in (DAMM,CPMM):
            if line.startswith("Program "+program+" invoke ["):
                events.append((program,"invoke"))
            elif line=="Program "+program+" success":
                events.append((program,"success"))
    if events!=[(DAMM,"invoke"),(DAMM,"success"),(CPMM,"invoke"),(CPMM,"success")]:
        report["status"]="ATOMIC_INVOCATION_ORDER_NOT_PROVEN"
        return report
    if not _cpi_intermediate_flow(tx,positive,keys[1]):
        report["status"]="INTERMEDIATE_CPI_FLOW_NOT_PROVEN"
        return report
    post=positive.get("accounts")
    if not isinstance(post,list) or len(post)!=3:
        report["status"]="MISSING_POST_STATE"
        return report
    from arb.token_vaults import decode_token_account
    amounts=[]
    for entry,mint in zip(post,(mint_x,mint_y,mint_z)):
        if not isinstance(entry,dict) or entry.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("atomic post token program invalid")
        token=decode_token_account(base64.b64decode(entry["data"][0],validate=True))
        if token["mint"]!=mint or token["authority"]!=owner:
            raise ValueError("atomic post mint or authority invalid")
        amounts.append(token["amount_base_units"])
    if not (0<amounts[0]<first_input and amounts[1]>=0
            and amounts[2]>=second_floor):
        report["status"]="ATOMIC_TERMINAL_BALANCES_NOT_PROVEN"
        return report
    if _post(rpc,keys,(mint_x,mint_y,mint_z),owner)!=before:
        raise ValueError("positive simulated transaction unexpectedly persisted")
    # Force second-leg slippage after a valid first leg. Error must be at
    # instruction index 1; first-leg error or missing blockhash is insufficient.
    ix2_bad=cpmm_instruction(cpmm_pool,cpmm,owner,keys[1],keys[2],
                             second_input,(1<<64)-1,
                             input_is_token_0=cpmm_direction,
                             expected_mints=None)
    bad=Transaction.new_signed_with_payer([ix1,ix2_bad],payer.pubkey(),[payer],bh)
    fail,_=_simulate(rpc,bad,keys)
    err=fail.get("err")
    error_instruction=(err.get("InstructionError")
                       if isinstance(err,dict) else None)
    negative_logs=fail.get("logs") or []
    rollback=(isinstance(error_instruction,list) and len(error_instruction)==2
              and error_instruction[0]==1
              and any(l=="Program "+DAMM+" success" for l in negative_logs)
              and any(l.startswith("Program "+CPMM+" invoke [") for l in negative_logs)
              and isinstance(fail.get("accounts"),list)
              and _post(rpc,keys,(mint_x,mint_y,mint_z),owner)==before)
    if rollback:
        negative_post=[]
        for entry,mint in zip(fail["accounts"],(mint_x,mint_y,mint_z)):
            if not isinstance(entry,dict) or entry.get("owner")!=TOKEN_PROGRAM:
                rollback=False
                break
            token=decode_token_account(base64.b64decode(entry["data"][0],validate=True))
            negative_post.append(token["amount_base_units"] if token["mint"]==mint and token["authority"]==owner else None)
        rollback=rollback and negative_post==before
    report.update(
        positive_post_balances_base_units=amounts,
        initial_balances_base_units=before,
        terminal_input_spent_base_units=first_input-amounts[0],
        terminal_output_received_base_units=amounts[2],
        intermediate_after_both_legs_base_units=amounts[1],
        intermediate_intra_transaction_consumption_verified=True,
        negative_error=str(err),
        negative_logs=negative_logs,
        rollback_failure_case_verified=bool(rollback),
        signed_atomic_simulation_verified=bool(rollback),
        status="SIGNED_ATOMIC_TWO_VENUE_AND_ROLLBACK_VERIFIED" if rollback
               else "SECOND_LEG_ROLLBACK_NOT_VERIFIED")
    return report


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("export","offline"))
    parser.add_argument("fixture")
    parser.add_argument("--output")
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--first-input",type=int,default=100000000)
    parser.add_argument("--second-input",type=int,default=1000)
    args=parser.parse_args()
    local_rpc_only(args.rpc)
    if args.mode=="export":
        result=export(args.rpc,args.fixture)
    else:
        if not args.output:
            parser.error("--output required")
        try:
            result=run(args.rpc,json.loads(Path(args.fixture).read_text()),
                       first_input=args.first_input,second_input=args.second_input)
        except Exception as exc:
            result={"status":"ATOMIC_EXECUTION_BLOCKED",
                    "error_class":type(exc).__name__,"diagnostic":str(exc)[:600],
                    "signed_atomic_simulation_verified":False,
                    "rollback_failure_case_verified":False,
                    "intermediate_intra_transaction_consumption_verified":False,
                    **SAFETY}
        Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"broadcast":False}))
    if args.mode=="offline" and result.get("signed_atomic_simulation_verified") is not True:
        raise SystemExit(2)


if __name__=="__main__":
    main()
