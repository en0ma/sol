"""Raydium CPMM swap-base-input instruction and local-only Surfpool simulation."""
import base64, hashlib, json, os, time
from arb.raydium_cpmm import PROGRAM,decode,verify_vaults
from arb.orca_whirlpool import SOL,USDC
from arb.rpc import call
from arb.whirlpool_simulation import TOKEN_SPACE,prepare_token_accounts,extract_balances
from arb.token_vaults import TOKEN_PROGRAM
DISCRIMINATOR=hashlib.sha256(b"global:swap_base_input").digest()[:8]
OUTPUT_DISCRIMINATOR=hashlib.sha256(b"global:swap_base_output").digest()[:8]
AUTH_SEED=b"vault_and_lp_mint_auth_seed"

def encode(amount_in,min_output):
    if any(type(x) is not int or not 0 <= x < (1<<64) for x in (amount_in,min_output)) or amount_in==0:
        raise ValueError("invalid CPMM amount")
    return DISCRIMINATOR+amount_in.to_bytes(8,"little")+min_output.to_bytes(8,"little")

def encode_exact_output(max_input,amount_out):
    if any(type(x) is not int or not 0 <= x < (1<<64) for x in (max_input,amount_out)) or amount_out==0 or max_input==0:
        raise ValueError("invalid CPMM exact-output amount")
    return OUTPUT_DISCRIMINATOR+max_input.to_bytes(8,"little")+amount_out.to_bytes(8,"little")

def instruction(pool,state,authority,user_a,user_b,amount_in,min_output,input_is_token_0=True,exact_output=False,*,expected_mints=(SOL,USDC)):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    program=Pubkey.from_string(PROGRAM)
    auth,bump=Pubkey.find_program_address([AUTH_SEED],program)
    if bump!=state["auth_bump"]: raise ValueError("Raydium pool authority bump mismatch")
    actual=(state["token_0_mint"],state["token_1_mint"])
    if len(set(actual))!=2:
        raise ValueError("duplicate Raydium token mint")
    if expected_mints is not None and set(actual)!=set(expected_mints):
        raise ValueError("unexpected token pair")
    if expected_mints == (SOL,USDC) and actual != (SOL,USDC):
        raise ValueError("legacy WSOL/USDC caller requires WSOL token0")
    if state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
        raise ValueError("only classic SPL token programs supported")
    if state.get("swap_enabled") is not True:
        raise ValueError("Raydium CPMM swaps disabled")
    if type(input_is_token_0) is not bool or type(exact_output) is not bool:
        raise ValueError("invalid swap direction or amount mode")
    input_vault=state["token_0_vault"] if input_is_token_0 else state["token_1_vault"]
    output_vault=state["token_1_vault"] if input_is_token_0 else state["token_0_vault"]
    input_mint=state["token_0_mint"] if input_is_token_0 else state["token_1_mint"]
    output_mint=state["token_1_mint"] if input_is_token_0 else state["token_0_mint"]
    input_program=state["token_0_program"] if input_is_token_0 else state["token_1_program"]
    output_program=state["token_1_program"] if input_is_token_0 else state["token_0_program"]
    keys=[(authority,True,True),(str(auth),False,False),(state["amm_config"],False,False),
          (pool,False,True),(user_a,False,True),(user_b,False,True),
          (input_vault,False,True),(output_vault,False,True),
          (input_program,False,False),(output_program,False,False),
          (input_mint,False,False),(output_mint,False,False),
          (state["observation"],False,True)]
    return Instruction(program,(encode_exact_output(amount_in,min_output) if exact_output else encode(amount_in,min_output)),[AccountMeta(Pubkey.from_string(k),s,w) for k,s,w in keys])

def run(rpc,pool,amount_in=1000000):
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    info=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])["value"]
    if not info or info["owner"]!=PROGRAM:raise ValueError("missing Raydium CPMM pool")
    state=decode(base64.b64decode(info["data"][0],validate=True))
    verify_vaults(rpc,pool,state)
    payer,a,b=Keypair(),Keypair(),Keypair()
    sig=call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000])
    if not isinstance(sig,str):raise ValueError("local payer airdrop failed")
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"]>=1000000000:break
        time.sleep(.25)
    else:raise ValueError("local airdrop balance unavailable")
    rent=call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    ixs=prepare_token_accounts(payer,a,b,state["token_0_mint"],state["token_1_mint"],True,rent,amount_in)
    ixs.append(instruction(pool,state,str(payer.pubkey()),str(a.pubkey()),str(b.pubkey()),amount_in,1))
    bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(ixs,payer.pubkey(),[payer,a,b],Hash.from_string(bh))
    if len(bytes(tx))>1232:raise ValueError("Solana packet too large")
    response=call(rpc,"simulateTransaction",[base64.b64encode(bytes(tx)).decode(),{
        "encoding":"base64","sigVerify":True,"commitment":"processed",
        "accounts":{"encoding":"base64","addresses":[str(a.pubkey()),str(b.pubkey())]}}])["value"]
    logs=response.get("logs") or []
    invoked=any("Program "+PROGRAM+" invoke" in l for l in logs)
    result={"status":"FAIL","swap_success":False,"program_invoked":invoked,
            "error":response.get("err"),"units":response.get("unitsConsumed"),
            "bytes":len(bytes(tx)),"pool":pool,"logs_tail":logs[-12:]}
    if response.get("err") is None and invoked:
        state2={"token_mint_a":state["token_0_mint"],"token_mint_b":state["token_1_mint"]}
        result["balances"]=extract_balances(response,str(a.pubkey()),str(b.pubkey()),state2,amount_in,True)
        result["swap_success"]=True
        result["status"]="PASS"
    return result


def capture_native_source(rpc,registry,output,*,count=8):
    """Authenticated CPMM source accounts; only source-eligible pools are captured."""
    from pathlib import Path
    from arb.next_ten_pair_fixture_export import program_data_accounts
    from arb.cpmm_config import decode_amm_config
    from arb.damm_cpmm_atomic_offline import _fetch
    from arb.pumpswap_local_simulation import local_rpc_only
    local_rpc_only(rpc)
    selected=[];rejected=[]
    for row in registry["pools"]:
        if row.get("venue")!="raydium_cpmm":continue
        addr=row["address"]
        try:
            info=call(rpc,"getAccountInfo",[addr,{"encoding":"base64","commitment":"confirmed"}])["value"]
            if not info or info.get("owner")!=PROGRAM or info.get("executable") is not False:
                raise ValueError("CPMM pool owner unavailable")
            state=decode(base64.b64decode(info["data"][0],validate=True))
            if not state["swap_enabled"] or state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
                raise ValueError("CPMM not enabled for classic-SPL native pricing")
            verify_vaults(rpc,addr,state,expected_mints=None)
            keys=[addr,state["token_0_vault"],state["token_1_vault"],
                  state["token_0_mint"],state["token_1_mint"],
                  state["amm_config"],state["observation"]]
            response=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
            vals=response.get("value");slot=response.get("context",{}).get("slot")
            if type(slot)is not int or not isinstance(vals,list) or any(not isinstance(x,dict) for x in vals):
                raise ValueError("CPMM source inventory missing")
            accounts=dict(zip(keys,vals))
            if accounts[addr]!=info:
                raise ValueError("CPMM pool mutated between authentication and snapshot")
            config_info=accounts[state["amm_config"]]
            if config_info["owner"]!=PROGRAM or config_info.get("executable") is not False:
                raise ValueError("CPMM config owner invalid")
            config=decode_amm_config(base64.b64decode(config_info["data"][0],validate=True))
            from solders.pubkey import Pubkey
            expected,bump=Pubkey.find_program_address([b"amm_config",config["index"].to_bytes(2,"big")],Pubkey.from_string(PROGRAM))
            if str(expected)!=state["amm_config"] or bump!=config["bump"]:
                raise ValueError("CPMM config PDA mismatch")
            config["fee_verified_onchain"]=True
            from arb.token_vaults import decode_token_account
            reserves=[]
            for i in (0,1):
                token=decode_token_account(base64.b64decode(accounts[state[f"token_{i}_vault"]]["data"][0],validate=True))
                if token["mint"]!=state[f"token_{i}_mint"]:
                    raise ValueError("CPMM vault mint mismatch")
                reserves.append(token["amount_base_units"])
            accounts.update(program_data_accounts(rpc,{PROGRAM}))
            selected.append({"pool":addr,"state":state,"config":config,
                             "accounts":accounts,"slot":slot,"reserves":reserves})
            if len(selected)>=count:break
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            rejected.append({"pool":addr,"reason":str(exc)[:220]})
    Path(output).write_text(json.dumps({"selected_pools":selected,"source_attempts":rejected},indent=2)+"\n")
    return len(selected)>=count


def native_signed_trial(rpc,captured,amount,input_is_token_0):
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    from arb.cpmm_quote import quote_source_exact_input
    from arb.orca_swap_v2_offline_provision import token_account_bytes
    from arb.m5_meteora_damm_v2_dedicated_signed_fork import _balances
    from arb.damm_cpmm_atomic_offline import _simulate
    from arb.orca_fork_clock import fork_clock,stable_orca_fork_clock
    state=captured["state"];pool=captured["pool"]
    mint_in=state["token_0_mint" if input_is_token_0 else "token_1_mint"]
    mint_out=state["token_1_mint" if input_is_token_0 else "token_0_mint"]
    signer=Keypair();owner=str(signer.pubkey())
    src,dst=str(Keypair().pubkey()),str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
         "data":"","owner":"11111111111111111111111111111111","executable":False}])
    for address,mint,balance in ((src,mint_in,amount),(dst,mint_out,0)):
        call(rpc,"surfnet_setAccount",[address,{"lamports":2039280,
             "data":token_account_bytes(mint,owner,balance).hex(),
             "owner":TOKEN_PROGRAM,"executable":False}])
    call(rpc,"surfnet_pauseClock",[])
    try:
        before=fork_clock(rpc)
        ix=instruction(pool,state,owner,src,dst,amount,1,
                       input_is_token_0=input_is_token_0,expected_mints=None)
        blockhash=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],Hash.from_string(blockhash))
        positive,_=_simulate(rpc,tx,[src,dst])
        if positive.get("err") is not None:
            raise ValueError("Raydium signed CPMM swap rejected: "+str(positive["err"])[:180])
        balances=_balances(positive,(mint_in,mint_out),owner)
        if balances[0]!=0 or balances[1]<=0:raise ValueError("CPMM exact-input SPL delta invalid")
        after=fork_clock(rpc)
        clock=stable_orca_fork_clock(before,after)
        if not clock["fork_clock_stable_for_quote"] or before["fork_clock_slot"]!=after["fork_clock_slot"]:
            raise ValueError("CPMM fork clock not stable")
        native=quote_source_exact_input(state,captured["config"],
            reserve_0=captured["reserves"][0],reserve_1=captured["reserves"][1],
            amount_in=amount,input_is_token_0=input_is_token_0,
            observed_unix=before["fork_unix_timestamp"])
        return {"status":"RAYDIUM_CPMM_SIGNED_NATIVE_EXACT" if native["amount_out"]==balances[1]
                       else "RAYDIUM_CPMM_SIGNED_NATIVE_MISMATCH",
                "pool":pool,"direction":"0_to_1" if input_is_token_0 else "1_to_0",
                "amount_in":amount,"native_output":native["amount_out"],
                "signed_output":balances[1],"signature":str(tx.signatures[0])}
    finally:
        call(rpc,"surfnet_resumeClock",[])


def validate_native_source(rpc,source,output,*,required=6,amounts=(1000000,10000000)):
    from pathlib import Path
    from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate
    reports=[]
    selected=source.get("selected_pools",[])
    for captured in selected:
        trials=[]
        try:
            hydrate(rpc,captured,program=PROGRAM)
            for direction in (True,False):
                for amount in amounts:
                    try:trials.append(native_signed_trial(rpc,captured,amount,direction))
                    except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                        trials.append({"status":"RAYDIUM_CPMM_SIGNED_BLOCKED","reason":str(exc)[:260]})
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            trials.append({"status":"RAYDIUM_CPMM_HYDRATION_BLOCKED","reason":str(exc)[:260]})
        exact=sum(t["status"]=="RAYDIUM_CPMM_SIGNED_NATIVE_EXACT" for t in trials)
        reports.append({"pool":captured["pool"],"exact_matches":exact,
            "trial_count":len(trials),"verified":exact==4 and len(trials)==4,"trials":trials})
    if len({r["pool"] for r in reports})!=len(reports):
        raise ValueError("duplicate Raydium signed pool identity")
    count=sum(r["verified"] for r in reports)
    report={"status":"RAYDIUM_CPMM_SIGNED_VERIFIED" if count>=required
                   else "RAYDIUM_CPMM_SIGNED_INCOMPLETE",
            "verified_pool_count":count,"required_verified_pools":required,
            "pools":reports,"actionable":False,"broadcast":False,"live_execution_approved":False}
    Path(output).write_text(json.dumps(report,indent=2)+"\\n")
    print(json.dumps({"status":report["status"],"verified_pool_count":count,
        "candidate_count":len(reports),"failed_pools":[{"pool":r["pool"],
        "reasons":[t.get("reason",t["status"]) for t in r["trials"] if t["status"]!="RAYDIUM_CPMM_SIGNED_NATIVE_EXACT"]}
        for r in reports if not r["verified"]]}))
    if count<required:raise SystemExit("six Raydium pools not exact signed verified")

def native_main():
    import argparse
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--registry");p.add_argument("--source-file",required=True)
    p.add_argument("--capture-source",action="store_true")
    p.add_argument("--output",required=True)
    p.add_argument("--pool-count",type=int,default=8)
    p.add_argument("--required-verified-pools",type=int,default=6)
    a=p.parse_args()
    rpc="http://127.0.0.1:8899"
    if a.capture_source:
        if not a.registry:raise SystemExit("registry required")
        ok=capture_native_source(rpc,json.loads(Path(a.registry).read_text()),a.source_file,count=a.pool_count)
        if not ok:raise SystemExit("insufficient CPMM source-eligible pools")
    else:
        validate_native_source(rpc,json.loads(Path(a.source_file).read_text()),
            a.output,required=a.required_verified_pools)

def main():
    with open("arb/raydium_cpmm_pools.json") as f:pools=json.load(f)["pools"]
    if not pools:return 2
    reports=[run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),p["address"]) for p in pools]
    print(json.dumps(reports,indent=2))
    return 0 if all(x["swap_success"] for x in reports) else 1
if __name__=="__main__":
    import sys
    if "--source-file" in sys.argv:native_main()
    else:raise SystemExit(main())
