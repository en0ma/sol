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
    step=60*state["tick_spacing"]
    start=start_tick(state["tick_current"],state["tick_spacing"])
    arrays=[tick_array_pda(pool,start),tick_array_pda(pool,start-step)]
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    instruction=build(pool,state,str(owner),input_ata,output_ata,
                      amount,1,arrays,input_is_token_0=True)
    wire=bytes(Transaction.new_signed_with_payer(
        [instruction],owner,[wallet],Hash.from_string(blockhash)))
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
            "token_account_funding_verified":False,
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
