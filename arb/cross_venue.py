"""Atomic Orca exact-output SOL->USDC, Raydium exact-input USDC->SOL.

All reads via local Surfpool; ephemeral funded account; simulateTransaction
only. Never broadcast. Independent pool state and SPL balances are checked.
"""
import base64,json,os,time
from arb.rpc import call
from arb.orca_whirlpool import SOL,USDC,PROGRAM as ORCA,fetch_pool
from arb.raydium_cpmm import PROGRAM as RAYDIUM,decode,verify_vaults
from arb.whirlpool_preflight import verify_oracle
from arb.whirlpool_swap import build_swap,inspect_swap_requirements
from arb.raydium_swap import instruction as raydium_instruction
from arb.whirlpool_simulation import prepare_token_accounts,TOKEN_SPACE
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

def measure(value, max_input):
    if value.get("err") is not None: raise ValueError("simulation errored")
    logs=value.get("logs") or []
    for program in (ORCA,RAYDIUM):
        if sum("Program "+program+" invoke" in s for s in logs)!=1:
            raise ValueError("venue invocation missing")
        if sum("Program "+program+" success" in s for s in logs)!=1:
            raise ValueError("venue did not succeed")
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("post-simulation accounts absent")
    amounts=[]
    for item,mint in zip(accounts,(SOL,USDC)):
        if not item or item.get("owner")!=TOKEN_PROGRAM:raise ValueError("wrong token owner")
        d=item.get("data")
        if not isinstance(d,list) or len(d)!=2 or d[1]!="base64":raise ValueError("bad returned token encoding")
        account=decode_token_account(base64.b64decode(d[0],validate=True))
        if account["mint"]!=mint: raise ValueError("unexpected final mint")
        amounts.append(account["amount_base_units"])
    if amounts[1]!=0:raise ValueError("USDC remains: route not closed")
    return {"starting_wsol_lamports":max_input,"final_wsol_lamports":amounts[0],
            "residual_usdc_base_units":amounts[1],
            "gross_wsol_change_lamports":amounts[0]-max_input,
            "venues_executed":2}

def run(rpc,orca_pool,raydium_pool,maximum_wsol_input=1000000,usdc_amount=10000,reverse=False):
    state=fetch_pool(rpc,orca_pool)
    if (state["token_mint_a"],state["token_mint_b"])!=(SOL,USDC):
        raise ValueError("requires Orca SOL token A, USDC token B")
    if not 0<usdc_amount<=100000 or not 0<maximum_wsol_input<=100000000:
        raise ValueError("unsafe test amounts")
    oracle=verify_oracle(rpc,orca_pool,
        adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
    readiness=inspect_swap_requirements(rpc,orca_pool)
    if not readiness["directions"]["b_to_a" if reverse else "a_to_b"]["available"]:
        return {"status":"BLOCKED_ORCA_TICKS","cross_venue_success":False}
    info=call(rpc,"getAccountInfo",[raydium_pool,{"encoding":"base64"}])["value"]
    if not info or info["owner"]!=RAYDIUM:raise ValueError("bad Raydium pool")
    cp=decode(base64.b64decode(info["data"][0],validate=True))
    verify_vaults(rpc,raydium_pool,cp)
    if (cp["token_0_mint"],cp["token_1_mint"])!=(SOL,USDC):
        raise ValueError("Raydium mint ordering incompatible")
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    payer,a,b=Keypair(),Keypair(),Keypair()
    sig=call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000])
    if not isinstance(sig,str):raise ValueError("local funding rejected")
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"]>=1000000000:break
        time.sleep(.25)
    else:raise ValueError("local payer funding missing")
    rent=call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    ixs=prepare_token_accounts(payer,a,b,SOL,USDC,True,rent,maximum_wsol_input)
    if reverse:
        # Raydium buys USDC first; Orca spends exact USDC for WSOL second.
        # A conservative fixed input must yield at least usdc_amount or the
        # entire atomic transaction fails, avoiding residual intermediate funds.
        ixs.append(raydium_instruction(raydium_pool,cp,str(payer.pubkey()),
            str(a.pubkey()),str(b.pubkey()),maximum_wsol_input,usdc_amount,True,exact_output=True))
        ixs.append(build_swap(orca_pool,state,str(payer.pubkey()),str(a.pubkey()),
            str(b.pubkey()),oracle,usdc_amount,1,False))
    else:
        ixs.append(build_swap(orca_pool,state,str(payer.pubkey()),str(a.pubkey()),
            str(b.pubkey()),oracle,usdc_amount,maximum_wsol_input,True,
            amount_specified_is_input=False))
        ixs.append(raydium_instruction(raydium_pool,cp,str(payer.pubkey()),
            str(b.pubkey()),str(a.pubkey()),usdc_amount,1,input_is_token_0=False))
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(ixs,payer.pubkey(),[payer,a,b],Hash.from_string(blockhash))
    wire=bytes(tx)
    if len(wire)>1232:
        return {"status":"TX_TOO_LARGE","cross_venue_success":False,"bytes":len(wire)}
    value=call(rpc,"simulateTransaction",[base64.b64encode(wire).decode(),{
        "encoding":"base64","sigVerify":True,"commitment":"processed",
        "accounts":{"encoding":"base64","addresses":[str(a.pubkey()),str(b.pubkey())]}}])["value"]
    output={"direction":"raydium_to_orca" if reverse else "orca_to_raydium",
        "status":"SIMULATION_FAILED","cross_venue_success":False,
        "error":value.get("err"),"compute_units":value.get("unitsConsumed"),
        "transaction_bytes":len(wire),"local_only":True,
        "log_tail":(value.get("logs") or [])[-18:]}
    if value.get("err") is not None:return output
    try:stats=measure(value,maximum_wsol_input)
    except ValueError as e:
        output["verification_error"]=str(e)
        return output
    try:
        fee=call(rpc,"getFeeForMessage",[base64.b64encode(bytes(tx.message)).decode()])["value"]
    except Exception:fee=None
    stats["estimated_network_fee_lamports"]=fee if type(fee) is int and fee>=0 else None
    stats["net_wsol_change_lamports"]=(stats["gross_wsol_change_lamports"]-fee
        if type(fee) is int and fee>=0 else None)
    output.update(stats)
    output["cross_venue_success"]=True
    output["status"]="PASS"
    output["profitable_after_fees"]=(stats["net_wsol_change_lamports"] is not None
                                     and stats["net_wsol_change_lamports"]>0)
    output["broadcast"]=False
    return output

def main():
    with open("arb/whirlpool_pools.json") as f:orca=json.load(f)["pools"][0]["address"]
    with open("arb/raydium_cpmm_pools.json") as f:raydium=json.load(f)["pools"][0]["address"]
    result=run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),orca,raydium)
    print(json.dumps(result,indent=2))
    return 0 if result["cross_venue_success"] else 1

if __name__=="__main__":raise SystemExit(main())
