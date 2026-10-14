"""Local-only, atomic Whirlpool swap simulation with ephemeral SPL token accounts.

Funds fee payer using Surfpool requestAirdrop, constructs System + SPL Token
account creation and a real Orca legacy swap instruction in ONE transaction.
The transaction is simulated, NEVER broadcast. No private keys are persisted.
"""
import base64
import json
import os
import time
from arb.rpc import call
from arb.orca_whirlpool import SOL, USDC, fetch_pool
from arb.whirlpool_preflight import verify_oracle
from arb.whirlpool_swap import build_swap, inspect_swap_requirements
from arb.token_vaults import TOKEN_PROGRAM

TOKEN_SPACE = 165

def token_ix(data, keys):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction, AccountMeta
    return Instruction(Pubkey.from_string(TOKEN_PROGRAM), data,
                       [AccountMeta(Pubkey.from_string(k), signer, writable)
                        for k, signer, writable in keys])

def prepare_token_accounts(payer, account_a, account_b, mint_a, mint_b,
                           input_is_a, rent_lamports, amount):
    """Create, initialize two owned token accounts and wrap local SOL input."""
    from solders.system_program import create_account, CreateAccountParams
    from solders.pubkey import Pubkey
    from solders.instruction import AccountMeta, Instruction
    if amount <= 0 or rent_lamports <= 0: raise ValueError("invalid funding")
    keys=(account_a,account_b)
    mints=(mint_a,mint_b)
    out=[]
    for i,(acct,mint) in enumerate(zip(keys,mints)):
        is_input=i==(0 if input_is_a else 1)
        lamports=rent_lamports+(amount if is_input else 0)
        out.append(create_account(CreateAccountParams(
            from_pubkey=payer.pubkey(), to_pubkey=acct.pubkey(),
            lamports=lamports, space=TOKEN_SPACE,
            owner=Pubkey.from_string(TOKEN_PROGRAM))))
        # SPL Token InitializeAccount3 = 18; owner in instruction data.
        out.append(Instruction(Pubkey.from_string(TOKEN_PROGRAM),
            bytes([18])+bytes(payer.pubkey()),
            [AccountMeta(acct.pubkey(),False,True),
             AccountMeta(Pubkey.from_string(mint),False,False)]))
        if is_input:
            # SPL Token SyncNative = 17. Only legitimate for WSOL.
            if mint!=SOL: raise ValueError("native input mint must be WSOL")
            out.append(Instruction(Pubkey.from_string(TOKEN_PROGRAM),bytes([17]),
                                   [AccountMeta(acct.pubkey(),False,True)]))
    return out

def run(rpc, pool_address, input_amount=1000000):
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    state=fetch_pool(rpc,pool_address)
    a_to_b=state["token_mint_a"]==SOL
    if {state["token_mint_a"],state["token_mint_b"]}!={SOL,USDC}:
        raise ValueError("only WSOL/USDC classic SPL Token pool supported")
    oracle=verify_oracle(rpc,pool_address,
                         adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
    readiness=inspect_swap_requirements(rpc,pool_address)
    direction="a_to_b" if a_to_b else "b_to_a"
    if not readiness["directions"][direction]["available"]:
        return {"status":"BLOCKED_TICK_ARRAYS","swap_success":False}
    payer, acct_a, acct_b=Keypair(),Keypair(),Keypair()
    if not isinstance(input_amount,int) or input_amount<=0 or input_amount>100000000:
        raise ValueError("unsafe input amount")
    funded=call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000])
    if not isinstance(funded,str): raise RuntimeError("Surfpool local airdrop not accepted")
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"]>=1000000000:
            break
        time.sleep(.25)
    else: raise RuntimeError("local-only payer funding missing")
    rent=call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    ixs=prepare_token_accounts(payer,acct_a,acct_b,state["token_mint_a"],
             state["token_mint_b"],a_to_b,rent,input_amount)
    ixs.append(build_swap(pool_address,state,str(payer.pubkey()),
                str(acct_a.pubkey()),str(acct_b.pubkey()),oracle,
                input_amount,1,a_to_b))
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(ixs,payer.pubkey(),
                         [payer,acct_a,acct_b],Hash.from_string(blockhash))
    wire=bytes(tx)
    if len(wire)>1232:
        raise ValueError("swap transaction exceeds Solana packet size")
    response=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode(),{"encoding":"base64",
                                       "sigVerify":True,"commitment":"processed"}])
    v=response.get("value",{})
    logs=v.get("logs") or []
    from arb.orca_whirlpool import PROGRAM
    invoked=any("Program "+PROGRAM+" invoke" in item for item in logs)
    succeeded=v.get("err") is None and invoked
    return {"status":"PASS" if succeeded else "SIMULATION_FAILED",
            "swap_success":succeeded,"program_invoked":invoked,"error":v.get("err"),
            "compute_units":v.get("unitsConsumed"),"transaction_bytes":len(wire),
            "pool":pool_address,"direction":direction,"local_only":True,
            "log_tail":logs[-12:]}

def main():
    with open("arb/whirlpool_pools.json") as f: pools=json.load(f)["pools"]
    if not pools: return 2
    report=[run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                p["address"]) for p in pools]
    print(json.dumps(report,indent=2))
    # Fail gate on non-executable swap; don't mask simulation failures.
    return 0 if all(r["swap_success"] for r in report) else 1

if __name__=="__main__":
    raise SystemExit(main())
