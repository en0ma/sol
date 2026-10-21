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

def main():
    with open("arb/raydium_cpmm_pools.json") as f:pools=json.load(f)["pools"]
    if not pools:return 2
    reports=[run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),p["address"]) for p in pools]
    print(json.dumps(reports,indent=2))
    return 0 if all(x["swap_success"] for x in reports) else 1
if __name__=="__main__":raise SystemExit(main())
