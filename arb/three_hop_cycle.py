"""Simulation-only CPMM WSOL->USDC -> CLMM USDC->RAY -> Orca RAY->WSOL.

Funds input exclusively with Surfpool local SOL airdrop; never mints or
broadcasts RAY/USDC. Executes only if account and transaction checks pass.
"""
import base64,json,os,time
from arb.rpc import call
from arb.orca_whirlpool import SOL,USDC
from arb.raydium_cpmm import decode as decode_cp,PROGRAM as CP,verify_vaults
from arb.raydium_clmm import decode as decode_cl,PROGRAM as CL,verify as verify_cl
from arb.raydium_clmm_ticks import inspect
from arb.raydium_clmm_swap import build
from arb.raydium_swap import instruction as cp_swap
from arb.whirlpool_simulation import prepare_token_accounts,TOKEN_SPACE
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.orca_whirlpool import PROGRAM as ORCA,fetch_pool
from arb.whirlpool_preflight import verify_oracle
from arb.whirlpool_swap import inspect_swap_requirements,build_swap

def check_balances(value,addresses,mints):
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=len(addresses):
        raise ValueError("missing simulated token accounts")
    amounts=[]
    for item,mint in zip(accounts,mints):
        if not item or item.get("owner")!=TOKEN_PROGRAM:raise ValueError("non-SPL output")
        data=item.get("data")
        if not isinstance(data,list) or data[1]!="base64":raise ValueError("invalid output encoding")
        parsed=decode_token_account(base64.b64decode(data[0],validate=True))
        if parsed["mint"]!=mint:raise ValueError("simulated output mint mismatch")
        amounts.append(parsed["amount_base_units"])
    if amounts[0]>=1000000 or amounts[2]<=0:
        raise ValueError("no input spent or no RAY received")
    return dict(zip(("remaining_wsol","residual_usdc","ray_received"),amounts))

def run(rpc,cp_pool,cl_pool,orca_pool):
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    from solders.pubkey import Pubkey
    from solders.system_program import create_account,CreateAccountParams
    from solders.instruction import Instruction,AccountMeta
    def read(pool,owner,decode):
        info=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}]).get("value")
        if not info or info.get("owner")!=owner:raise ValueError("wrong pool owner")
        return decode(base64.b64decode(info["data"][0],validate=True))
    cp=read(cp_pool,CP,decode_cp);verify_vaults(rpc,cp_pool,cp)
    cl=read(cl_pool,CL,decode_cl);verify_cl(rpc,cl_pool,cl)
    if (cp["token_0_mint"],cp["token_1_mint"])!=(SOL,USDC):
        raise ValueError("incompatible CPMM pool")
    if cl["token_mint_1"]!=USDC:raise ValueError("CLMM is not token1 USDC")
    readiness=inspect(rpc,cl_pool,zero_for_one=False)
    if not readiness["all_arrays_valid"]:
        return {"status":"BLOCKED_CLMM_TICKS","swap_success":False}
    oc=fetch_pool(rpc,orca_pool)
    ray_mint=cl["token_mint_0"]
    if (oc["token_mint_a"],oc["token_mint_b"])!=(SOL,ray_mint):
        raise ValueError("third leg must have WSOL token A and RAY token B")
    oracle=verify_oracle(rpc,orca_pool,
         adaptive_fee=oc["tick_spacing"]!=oc["fee_tier_index_seed"])
    requirements=inspect_swap_requirements(rpc,orca_pool)
    if not requirements["directions"]["b_to_a"]["available"]:
        return {"status":"BLOCKED_ORCA_TICKS","cycle_closed":False}
    payer,wsol,usdc,ray=Keypair(),Keypair(),Keypair(),Keypair()
    if not isinstance(call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000]),str):
        raise ValueError("local airdrop failed")
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"]>=1000000000:break
        time.sleep(.25)
    else:raise ValueError("local funding unavailable")
    rent=call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    ixs=prepare_token_accounts(payer,wsol,usdc,SOL,USDC,True,rent,1000000)
    ixs.extend([create_account(CreateAccountParams(from_pubkey=payer.pubkey(),
        to_pubkey=ray.pubkey(),lamports=rent,space=TOKEN_SPACE,
        owner=Pubkey.from_string(TOKEN_PROGRAM))),
        Instruction(Pubkey.from_string(TOKEN_PROGRAM),bytes([18])+bytes(payer.pubkey()),
                    [AccountMeta(ray.pubkey(),False,True),
                     AccountMeta(Pubkey.from_string(cl["token_mint_0"]),False,False)])])
    ixs.append(cp_swap(cp_pool,cp,str(payer.pubkey()),str(wsol.pubkey()),
                       str(usdc.pubkey()),1000000,10000,exact_output=True))
    ixs.append(build(cl_pool,cl,str(payer.pubkey()),str(usdc.pubkey()),
                     str(ray.pubkey()),10000,1,[a["address"] for a in
                     readiness["tick_arrays"]],input_is_token_0=False))
    ixs.append(build_swap(orca_pool,oc,str(payer.pubkey()),
             str(wsol.pubkey()),str(ray.pubkey()),oracle,5427,1,False))
    bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(ixs,payer.pubkey(),
                                          [payer,wsol,usdc,ray],Hash.from_string(bh))
    legacy_size=len(bytes(tx))
    if legacy_size>1232:
        table=os.environ.get("SURFPOOL_CLMM_ALT_ADDRESS")
        from arb.clmm_v0 import load_table,build_v0
        from arb.clmm_local_alt import provision,require_local
        try:
            if table:lookup=load_table(rpc,table)
            else:
                require_local(rpc)
                keys=[]
                for ix in ixs:
                    for meta in ix.accounts:
                        key=str(meta.pubkey)
                        if not meta.is_signer and key not in keys:keys.append(key)
                    key=str(ix.program_id)
                    if key not in keys:keys.append(key)
                lookup=provision(rpc,payer,keys[:24])
            bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
            tx=build_v0(ixs,payer,[payer,wsol,usdc,ray],bh,[lookup])
        except ValueError as exc:
            return {"status":"ALT_UNAVAILABLE","swap_success":False,
                    "legacy_transaction_bytes":legacy_size,"reason":str(exc),
                    "broadcast":False}
    value=call(rpc,"simulateTransaction",[base64.b64encode(bytes(tx)).decode(),{
        "encoding":"base64","sigVerify":True,"commitment":"processed",
        "accounts":{"encoding":"base64","addresses":[str(wsol.pubkey()),
                      str(usdc.pubkey()),str(ray.pubkey())]}}])["value"]
    logs=value.get("logs") or []
    done=value.get("err") is None and all(
        any("Program "+program+" success" in line for line in logs)
        for program in (CP,CL,ORCA))
    result={"status":"SIMULATION_FAILED","swap_success":False,"cycle_closed":False,
            "error":value.get("err"),"compute_units":value.get("unitsConsumed"),
            "transaction_bytes":len(bytes(tx)),"log_tail":logs[-16:],
            "broadcast":False}
    if done:
        try:
            results=check_balances(value,[str(wsol.pubkey()),str(usdc.pubkey()),
                         str(ray.pubkey())],[SOL,USDC,cl["token_mint_0"]])
            if results["residual_usdc"]!=0:raise ValueError("unspent intermediate USDC")
            amount_wsol=results["remaining_wsol"]
            residual_ray=results["ray_received"]
            closed=(results["residual_usdc"]==0 and residual_ray==0)
            result.update(results,status="PASS" if closed else "RESIDUAL_INTERMEDIATE",
                          swaps_executed=3,cycle_closed=closed,swap_success=closed,
                          gross_wsol_change_lamports=amount_wsol-1000000)
            try:
                fee=call(rpc,"getFeeForMessage",[base64.b64encode(bytes(tx.message)).decode()]).get("value")
            except Exception:fee=None
            result["estimated_network_fee_lamports"]=fee if type(fee)is int and fee>=0 else None
            result["net_wsol_change_lamports"]=(amount_wsol-1000000-fee if type(fee)is int and fee>=0 else None)
            result["profitable"]=closed and result["net_wsol_change_lamports"] is not None and result["net_wsol_change_lamports"]>0
        except ValueError as exc:result["balance_error"]=str(exc)
    return result

def main():
    cp=json.load(open("arb/pool_registry.json"))["pools"]
    cpa=next(x["address"] for x in cp if x["venue"]=="raydium_cpmm")
    cla=next(x["address"] for x in cp if x["venue"]=="raydium_clmm")
    oca=next(x["address"] for x in cp if x["venue"]=="orca" and "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R" in x.get("mints",[]))
    try:out=run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),cpa,cla,oca)
    except Exception as exc:out={"status":"BLOCKED","swap_success":False,
                                 "error":str(exc)[:200]}
    print(json.dumps(out,indent=2))
    if os.environ.get("THREE_HOP_REPORT"):
        with open(os.environ["THREE_HOP_REPORT"],"w") as f:json.dump(out,f,indent=2)
    return 0 if out.get("cycle_closed") else 2

if __name__=="__main__":raise SystemExit(main())
