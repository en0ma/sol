"""Signed Meteora DLMM exact-input diagnostic on a separate offline Surfpool.

All state writes are gated to SURFPOOL_EXPLICITLY_OFFLINE=1 and loopback.
Only simulateTransaction; no sendTransaction or live execution.
"""
import base64
import json
import os
import sys
from pathlib import Path
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call, RPCError
from arb.meteora_dlmm import PROGRAM
from arb.meteora_dlmm_swap import build_swap
from arb.orca_three_hop_offline_simulation import offline_gate, LOADER, SYSTEM
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

MAX_TX_BYTES=1232
AMOUNT_IN=1000000

def attempt(rpc,fixture):
    offline_gate(rpc)
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or fixture.get("venue")!="meteora_dlmm":
        raise ValueError("authenticated read-only DLMM fixture required")
    accounts=fixture["accounts"]
    pool=fixture["pool"]
    state=fixture["pool_state"]
    preflight=fixture["preflight"]
    if preflight.get("status")!="ACTIVE_BIN_ARRAY_AUTHENTICATED" or preflight.get("pool")!=pool:
        raise ValueError("authenticated DLMM preflight required")
    if preflight.get("oracle_evidence",{}).get("oracle")!=state["oracle"]:
        raise ValueError("DLMM oracle mismatch")
    prog=accounts[PROGRAM]
    raw=base64.b64decode(prog["data"][0],validate=True)
    if prog.get("owner")!=LOADER or prog.get("executable") is not True or raw[:4]!=bytes([2,0,0,0]):
        raise ValueError("invalid authenticated DLMM executable")
    pd_address=str(Pubkey.from_bytes(raw[4:36]))
    pd=accounts[pd_address]
    pd_raw=base64.b64decode(pd["data"][0],validate=True)
    if pd.get("owner")!=LOADER or pd_raw[:4]!=bytes([3,0,0,0]) or pd_raw[45:49]!=bytes([127])+b"ELF":
        raise ValueError("invalid DLMM ELF")
    for address,info in accounts.items():
        if address in (PROGRAM,pd_address):
            continue
        if not isinstance(info,dict) or info["data"][1]!="base64":
            raise ValueError("invalid DLMM fixture account")
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":info["lamports"],"data":base64.b64decode(info["data"][0],validate=True).hex(),
            "owner":info["owner"],"executable":info["executable"]}])
    elf=pd_raw[45:]
    for offset in range(0,len(elf),16384):
        call(rpc,"surfnet_writeProgram",[PROGRAM,elf[offset:offset+16384].hex(),offset])
    signer=Keypair()
    authority=str(signer.pubkey())
    call(rpc,"surfnet_setAccount",[authority,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    mint_in,mint_out=state["token_x_mint"],state["token_y_mint"]
    if any(accounts[m]["owner"]!=TOKEN_PROGRAM for m in (mint_in,mint_out)):
        raise ValueError("classic SPL mint accounts required")
    user_in,user_out=str(Keypair().pubkey()),str(Keypair().pubkey())
    for address,mint,amount in ((user_in,mint_in,AMOUNT_IN),(user_out,mint_out,0)):
        call(rpc,"surfnet_setAccount",[address,{"lamports":2039280,
            "data":token_account_bytes(mint,authority,amount).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    bins=[row["pda"] for row in preflight["neighboring_bin_arrays"]
          if row.get("authenticated")]
    swap_state=dict(state,input_mint=mint_in,output_mint=mint_out,
                    active_bin_array_index=preflight["active_bin_array_index"])
    instruction=build_swap(pool,swap_state,authority,user_in,user_out,
                           state["oracle"],bins,AMOUNT_IN,1,input_is_x=True)
    bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(
        [instruction],signer.pubkey(),[signer],Hash.from_string(bh))
    wire=bytes(tx)
    report={"status":"SIGNED_DLMM_SIMULATION_NOT_ATTEMPTED",
            "transaction_bytes":len(wire),"authenticated_bin_arrays":len(bins),
            "input_base_units":AMOUNT_IN,"input_mint":mint_in,"output_mint":mint_out,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
    if len(wire)>MAX_TX_BYTES:
        return dict(report,status="DLMM_TRANSACTION_OVER_PACKET_LIMIT")
    def persistent_balances():
        response=call(rpc,"getMultipleAccounts",[[user_in,user_out],{"encoding":"base64"}])
        values=response.get("value")
        if not isinstance(values,list) or len(values)!=2:
            raise ValueError("missing persistent DLMM accounts")
        result=[]
        for account,mint in zip(values,(mint_in,mint_out)):
            if not account or account.get("owner")!=TOKEN_PROGRAM:
                raise ValueError("DLMM persistent token owner mismatch")
            dec=decode_token_account(base64.b64decode(account["data"][0],validate=True))
            if dec["mint"]!=mint or dec["authority"]!=authority:
                raise ValueError("DLMM persistent token mint/authority mismatch")
            result.append(dec["amount_base_units"])
        return result
    before=persistent_balances()
    if before!=[AMOUNT_IN,0]:
        raise ValueError("offline DLMM starting account balances invalid")
    result=call(rpc,"simulateTransaction",[base64.b64encode(wire).decode(),{
        "encoding":"base64","sigVerify":True,
        "accounts":{"encoding":"base64","addresses":[user_in,user_out]}}])
    after=persistent_balances()
    report["simulation_did_not_persist"]=after==before
    if after!=before:
        raise ValueError("DLMM signed simulation changed persistent token balances")
    report["signed_simulation_requested"]=True
    value=result.get("value")
    if not isinstance(value,dict):
        return dict(report,status="DLMM_SIMULATION_RPC_REJECTED",rpc_error=str(result)[:400])
    report.update(simulation_error=value.get("err"),
                  compute_units=value.get("unitsConsumed"),logs_tail=(value.get("logs") or [])[-24:])
    if value.get("err") is not None:
        return dict(report,status="SIGNED_DLMM_SIMULATION_FAILED")
    logs=value.get("logs") or []
    if not any("Program "+PROGRAM+" success" in x for x in logs):
        return dict(report,status="DLMM_PROGRAM_SUCCESS_LOG_MISSING")
    returned=value.get("accounts")
    if not isinstance(returned,list) or len(returned)!=2 or any(x is None for x in returned):
        return dict(report,status="DLMM_SIMULATED_ACCOUNTS_UNAVAILABLE")
    decoded=[decode_token_account(base64.b64decode(x["data"][0],validate=True)) for x in returned]
    if decoded[0]["mint"]!=mint_in or decoded[1]["mint"]!=mint_out or any(x["authority"]!=authority for x in decoded):
        raise ValueError("DLMM simulated output account mismatch")
    report["simulated_input_remaining_base_units"]=decoded[0]["amount_base_units"]
    report["simulated_input_spent_base_units"]=before[0]-decoded[0]["amount_base_units"]
    report["simulated_output_base_units"]=decoded[1]["amount_base_units"]
    if (decoded[0]["amount_base_units"]>=AMOUNT_IN or
            decoded[1]["amount_base_units"]<=0 or
            decoded[0]["amount_base_units"]<0):
        return dict(report,status="DLMM_TOKEN_BALANCE_CHANGE_INVALID")
    report["status"]="SIGNED_DLMM_STANDALONE_SIMULATED"
    return report

def main():
    report={"status":"DLMM_OFFLINE_NOT_STARTED","actionable":False,
            "live_execution_approved":False,"broadcast":False}
    try:
        rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
        offline_gate(rpc)
        report=attempt(rpc,json.loads(Path(sys.argv[1]).read_text()))
    except (RPCError,ValueError,KeyError,TypeError,OSError,TimeoutError,IndexError) as exc:
        report=dict(report,status="DLMM_OFFLINE_BLOCKED",reason=str(exc)[:500])
    Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
