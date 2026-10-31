"""Signed two-venue closed cycle, entirely inside isolated Surfpool --offline.

Hydrates a verified read-only Orca/Meteora fixture, simulates the first
DLMM leg for a chained amount, then simulates both legs atomically.
No transaction broadcast or live execution.
"""
import base64
import json
import os
import sys
from pathlib import Path
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.transaction import Transaction
from arb.rpc import call, RPCError
from arb.orca_whirlpool import PROGRAM as ORCA, SOL, fetch_pool
from arb.meteora_dlmm import PROGRAM as DLMM, decode as decode_dlmm
from arb.mixed_cycle_assembler import assemble_mixed_cycle
from arb.orca_three_hop_offline_simulation import offline_gate, LOADER, SYSTEM, assess_cycle_economics
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

INPUT_LAMPORTS=1000000
MAX_TX_BYTES=1232

def simulate(rpc,instructions,signer,addresses):
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(
        instructions,signer.pubkey(),[signer],Hash.from_string(blockhash))
    raw=bytes(tx)
    if len(raw)>MAX_TX_BYTES:
        raise ValueError("mixed signed transaction exceeds Solana packet limit")
    response=call(rpc,"simulateTransaction",[base64.b64encode(raw).decode(),{
        "encoding":"base64","sigVerify":True,"accounts":{
            "encoding":"base64","addresses":addresses}}])
    return tx,response.get("value",{}),len(raw)

def attempt(rpc,fixture):
    offline_gate(rpc)
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("untrusted mixed fixture provenance")
    route=fixture["route"]
    legs,tokens=route["legs"],route["tokens"]
    if (len(legs)!=2 or len(tokens)!=3 or tokens[0]!=SOL or tokens[-1]!=SOL
        or [leg.get("venue") for leg in legs]!=["meteora_dlmm","orca"]
        or any(leg.get("from")!=tokens[i] or leg.get("to")!=tokens[i+1] for i,leg in enumerate(legs))):
        raise ValueError("only verified DLMM-then-Orca closed route supported")
    accounts=fixture["accounts"]
    evidence=fixture["leg_evidence"]
    programdata_addresses=set()
    for program in (ORCA,DLMM):
        info=accounts[program]
        raw=base64.b64decode(info["data"][0],validate=True)
        if info.get("owner")!=LOADER or info.get("executable") is not True or raw[:4]!=bytes([2,0,0,0]):
            raise ValueError("invalid executable venue program")
        pd_addr=str(Pubkey.from_bytes(raw[4:36]))
        pd=accounts[pd_addr]
        binary=base64.b64decode(pd["data"][0],validate=True)
        if pd.get("owner")!=LOADER or binary[:4]!=bytes([3,0,0,0]) or binary[45:49]!=bytes([127])+b"ELF":
            raise ValueError("invalid authenticated venue ELF")
        programdata_addresses.add(pd_addr)
    for addr,info in accounts.items():
        if addr in (ORCA,DLMM) or addr in programdata_addresses:
            continue
        if info is None:
            # Only a verified optional Orca oracle may be absent.
            if addr!=evidence[legs[1]["pool"]]["oracle"]:
                raise ValueError("unverified missing account: "+addr)
            continue
        if info["data"][1]!="base64":
            raise ValueError("fixture account has unsupported encoding")
        call(rpc,"surfnet_setAccount",[addr,{
            "lamports":info["lamports"],"data":base64.b64decode(info["data"][0],validate=True).hex(),
            "owner":info["owner"],"executable":info["executable"]}])
    for program in (ORCA,DLMM):
        info=accounts[program]
        pd_addr=str(Pubkey.from_bytes(base64.b64decode(info["data"][0],validate=True)[4:36]))
        elf=base64.b64decode(accounts[pd_addr]["data"][0],validate=True)[45:]
        for off in range(0,len(elf),16384):
            call(rpc,"surfnet_writeProgram",[program,elf[off:off+16384].hex(),off])
    signer=Keypair()
    authority=str(signer.pubkey())
    call(rpc,"surfnet_setAccount",[authority,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    user_accounts={}
    for mint in tokens[:-1]:
        if accounts[mint]["owner"]!=TOKEN_PROGRAM:
            raise ValueError("nonclassic user mint unsupported")
        address=str(Keypair().pubkey())
        amount=INPUT_LAMPORTS if mint==SOL else 0
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,"data":token_account_bytes(mint,authority,amount).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
        user_accounts[mint]=address
    def balances():
        res=call(rpc,"getMultipleAccounts",[
            [user_accounts[m] for m in tokens[:-1]],{"encoding":"base64"}])
        output={}
        for mint,item in zip(tokens[:-1],res["value"]):
            if not item or item["owner"]!=TOKEN_PROGRAM:
                raise ValueError("persisted offline account missing")
            decoded=decode_token_account(base64.b64decode(item["data"][0],validate=True))
            if decoded["mint"]!=mint or decoded["authority"]!=authority:
                raise ValueError("persisted token account mismatch")
            output[mint]=decoded["amount_base_units"]
        return output
    if balances()!={SOL:INPUT_LAMPORTS,tokens[1]:0}:
        raise ValueError("incorrect offline starting balances")
    dlmm_leg,orca_leg=legs
    dlmm_info=accounts[dlmm_leg["pool"]]
    dlmm_state=decode_dlmm(base64.b64decode(dlmm_info["data"][0],validate=True))
    pre=evidence[dlmm_leg["pool"]]["preflight"]
    dlmm_state.update(oracle=dlmm_state["oracle"],
        authenticated_bin_arrays=evidence[dlmm_leg["pool"]]["authenticated_bin_arrays"],
        active_bin_array_index=pre["active_bin_array_index"])
    orca_state=fetch_pool(rpc,orca_leg["pool"])
    states={dlmm_leg["pool"]:dlmm_state,orca_leg["pool"]:orca_state}
    oracles={dlmm_leg["pool"]:dlmm_state["oracle"],
             orca_leg["pool"]:evidence[orca_leg["pool"]]["oracle"]}
    first=assemble_mixed_cycle(
        {"tokens":[SOL,tokens[1],SOL],"legs":[dlmm_leg,{
            "venue":"orca","pool":orca_leg["pool"],
            "from":tokens[1],"to":SOL}]},
        states,oracles,user_accounts,authority,[INPUT_LAMPORTS,1],[1,1])[0]
    _,quote,size=simulate(rpc,[first],signer,[user_accounts[tokens[1]]])
    report={"status":"MIXED_ATOMIC_NOT_ATTEMPTED",
        "route":tokens,"first_leg_quote_tx_bytes":size,
        "first_leg_error":quote.get("err"),
        "first_leg_compute_units":quote.get("unitsConsumed"),
        "actionable":False,"live_execution_approved":False,"broadcast":False}
    if quote.get("err") is not None:
        return dict(report,status="DLMM_FIRST_LEG_QUOTE_FAILED",
                    logs_tail=(quote.get("logs") or [])[-15:])
    posted=quote.get("accounts")
    if not isinstance(posted,list) or len(posted)!=1 or not posted[0]:
        raise ValueError("first leg simulated output account missing")
    output=decode_token_account(base64.b64decode(posted[0]["data"][0],validate=True))
    if output["mint"]!=tokens[1] or output["authority"]!=authority:
        raise ValueError("first leg output mint/authority mismatch")
    quantity=output["amount_base_units"]
    if quantity<=0:
        return dict(report,status="DLMM_FIRST_LEG_ZERO_OUTPUT")
    report["first_leg_output_base_units"]=quantity
    instructions=assemble_mixed_cycle(route,states,oracles,user_accounts,
        authority,[INPUT_LAMPORTS,quantity],[1,1])
    before=balances()
    tx,result,tx_bytes=simulate(rpc,instructions,signer,
                               [user_accounts[SOL],user_accounts[tokens[1]]])
    after=balances()
    if after!=before:
        raise ValueError("mixed atomic simulation persisted token mutations")
    report.update(signed_atomic_simulation_requested=True,
        simulation_did_not_persist=True,transaction_bytes=tx_bytes,
        simulation_error=result.get("err"),compute_units=result.get("unitsConsumed"),
        logs_tail=(result.get("logs") or [])[-24:])
    if result.get("err") is not None:
        return dict(report,status="MIXED_ATOMIC_SIMULATION_FAILED")
    logs=result.get("logs") or []
    if not all(any("Program "+program+" success" in line for line in logs)
               for program in (DLMM,ORCA)):
        return dict(report,status="MIXED_VENUE_SUCCESS_LOG_MISSING")
    values=result.get("accounts")
    if not isinstance(values,list) or len(values)!=2 or any(v is None for v in values):
        raise ValueError("post-simulation mixed token accounts missing")
    observed={}
    for mint,item in zip(tokens[:-1],values):
        if item["owner"]!=TOKEN_PROGRAM:
            raise ValueError("post-simulation owner mismatch")
        decoded=decode_token_account(base64.b64decode(item["data"][0],validate=True))
        if decoded["mint"]!=mint or decoded["authority"]!=authority:
            raise ValueError("post-simulation token identity mismatch")
        observed[mint]=decoded["amount_base_units"]
    report["final_balances_base_units"]=observed
    if observed[tokens[1]]!=0:
        return dict(report,status="MIXED_RESIDUAL_INTERMEDIATE_TOKEN")
    try:
        fee=call(rpc,"getFeeForMessage",[
            base64.b64encode(bytes(tx.message)).decode()]).get("value")
    except (RPCError,ValueError,TypeError,KeyError):
        fee=None
    if type(fee)is not int or fee<0:
        fee=None
    report["economics"]=assess_cycle_economics(INPUT_LAMPORTS,observed[SOL],fee)
    report["status"]="MIXED_ATOMIC_SIMULATED_"+report["economics"]["status"]
    return report

def main():
    report={"status":"MIXED_OFFLINE_NOT_STARTED","actionable":False,
            "live_execution_approved":False,"broadcast":False}
    try:
        rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
        offline_gate(rpc)
        report=attempt(rpc,json.loads(Path(sys.argv[1]).read_text()))
    except (RPCError,ValueError,KeyError,TypeError,OSError,TimeoutError,IndexError) as exc:
        report=dict(report,status="MIXED_OFFLINE_BLOCKED",reason=str(exc)[:500])
    Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!="logs_tail"},indent=2))

if __name__=="__main__":
    main()
