"""Attempt a signed CLMM swap_v2 on localhost Surfpool; report failures honestly.

Uses a fresh ephemeral wallet with unfunded SPL ATAs. This diagnoses the
transaction instruction and funding prerequisites; never broadcasts.
"""
import json,os
from arb.rpc import call
from arb.raydium_clmm_fee_snapshot import read
from arb.raydium_clmm_swap import build,TOKEN_2022
from arb.raydium_clmm_ticks import start_tick,tick_array_pda
from arb.pumpswap_local_simulation import local_rpc_only
from arb.token_vaults import TOKEN_PROGRAM

ATA_PROGRAM="ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"

def probe(rpc,pool,amount=100000):
    local_rpc_only(rpc)
    if type(amount)is not int or not 0<amount<1<<64:
        raise ValueError("invalid CLMM simulation input")
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.transaction import Transaction
    from solders.instruction import Instruction,AccountMeta
    wallet=Keypair()
    state=read(rpc,pool)["state"]
    owner=wallet.pubkey()
    # Fund only the ephemeral fee payer on the local fork.
    call(rpc,"requestAirdrop",[str(owner),100000000])
    import time
    for _ in range(30):
        if call(rpc,"getBalance",[str(owner)])["value"]>=100000000:
            break
        time.sleep(0.25)
    else:
        raise ValueError("local fee payer airdrop not reflected")
    token_program=Pubkey.from_string(TOKEN_PROGRAM)
    ata_program=Pubkey.from_string(ATA_PROGRAM)
    def ata(mint):
        return str(Pubkey.find_program_address(
            [bytes(owner),bytes(token_program),bytes(Pubkey.from_string(mint))],
            ata_program)[0])
    input_ata=ata(state["token_mint_0"])
    output_ata=ata(state["token_mint_1"])
    # Surfpool-only cheatcode creates and funds the owner's canonical ATA.
    # The amount is synthetic local test liquidity, never a mainnet balance.
    call(rpc,"surfnet_setTokenAccount",[
        str(owner),state["token_mint_0"],
        {"amount":amount*10,"state":"initialized"},TOKEN_PROGRAM])
    from arb.token_vaults import decode_token_account
    import base64
    account=call(rpc,"getAccountInfo",[
        input_ata,{"encoding":"base64","commitment":"processed"}])["value"]
    if not account or account.get("owner")!=TOKEN_PROGRAM:
        raise ValueError("Surfpool-funded input ATA unavailable")
    token=decode_token_account(base64.b64decode(account["data"][0],validate=True))
    if (token["mint"]!=state["token_mint_0"] or
            token["authority"]!=str(owner) or token["amount_base_units"]<amount):
        raise ValueError("Surfpool synthetic token funding failed verification")
    step=60*state["tick_spacing"]
    start=start_tick(state["tick_current"],state["tick_spacing"])
    arrays=[tick_array_pda(pool,start),tick_array_pda(pool,start-step)]
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    def create_ata(address,mint):
        # Idempotent ATA creation, included in the signed simulation only.
        keys=[(owner,True,True),(Pubkey.from_string(address),False,True),
              (owner,False,False),(Pubkey.from_string(mint),False,False),
              (Pubkey.from_string("11111111111111111111111111111111"),False,False),
              (token_program,False,False)]
        return Instruction(ata_program,bytes([1]),
            [AccountMeta(key,signer,writable) for key,signer,writable in keys])
    setup=[create_ata(output_ata,state["token_mint_1"])]
    instruction=build(pool,state,str(owner),input_ata,output_ata,
                      amount,1,arrays,input_is_token_0=True)
    wire=bytes(Transaction.new_signed_with_payer(
        [*setup,instruction],owner,[wallet],Hash.from_string(blockhash)))
    import base64
    result=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode("ascii"),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "commitment":"processed"}])["value"]
    error=result.get("err")
    logs=result.get("logs")
    return {"status":"SIGNED_SIMULATION_SUCCESS" if error is None else "SIGNED_SIMULATION_FAILED",
            "pool":pool,"amount_in":amount,"simulation_error":error,
            "logs_tail":logs[-8:] if isinstance(logs,list) else [],
            "signed":True,"local_only":True,"broadcast":False,
            "fee_payer_funded_on_fork":True,
            "ata_creation_in_simulated_transaction":True,
            "token_account_funding_verified":True,
            "synthetic_local_input_tokens":True,
            "post_swap_balances_verified":False,
            "executable_route_verified":False,"profitable_arbitrage_verified":False}

def main():
    with open("arb/pool_registry.json") as f: pools=json.load(f)["pools"]
    pool=next(p["address"] for p in pools if p["venue"]=="raydium_clmm")
    result=probe(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),pool)
    print(json.dumps(result,indent=2))
    if os.environ.get("CLMM_SIGNED_PROBE_REPORT"):
        with open(os.environ["CLMM_SIGNED_PROBE_REPORT"],"w") as f:
            json.dump(result,f,indent=2)

if __name__=="__main__":main()
