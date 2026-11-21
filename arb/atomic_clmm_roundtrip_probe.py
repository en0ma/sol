"""Attempt a signed two-leg RAY/USDC/RAY CLMM round trip on Surfpool.

A deterministic execution probe, NOT an arbitrage opportunity. Both legs
execute in one simulation transaction and the entire route's post-balances are
authenticated. No sendTransaction or mainnet token creation.
"""
import base64,json,os,time
from arb.rpc import call
from arb.raydium_clmm_fee_snapshot import read
from arb.raydium_clmm_live_quote import quote_live
from arb.raydium_clmm_swap import build
from arb.raydium_clmm_ticks import start_tick,tick_array_pda
from arb.raydium_clmm_signed_probe import ATA_PROGRAM
from arb.atomic_cycle_builder import sign_atomic
from arb.atomic_cycle_simulation import verify_atomic_cycle
from arb.pumpswap_local_simulation import local_rpc_only
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account


def probe(rpc,pool,amount=100000):
    local_rpc_only(rpc)
    if type(amount)is not int or not 0<amount<1<<64:
        raise ValueError("invalid atomic swap input")
    from solders.pubkey import Pubkey
    from solders.keypair import Keypair
    from solders.instruction import Instruction,AccountMeta
    wallet=Keypair()
    owner=wallet.pubkey()
    state=read(rpc,pool)["state"]
    mint_a,mint_b=state["token_mint_0"],state["token_mint_1"]
    quote_a=quote_live(rpc,pool,mint_a,amount)
    intermediate=quote_a["estimated_output_base_units"]
    if type(intermediate)is not int or not 0<intermediate<1<<64:
        raise ValueError("first leg is not quotable")
    # Second-leg amount is fixed before signing; if the first leg produces
    # less than quoted the atomic transaction must fail, never silently resize.
    quote_b=quote_live(rpc,pool,mint_b,intermediate)
    call(rpc,"requestAirdrop",[str(owner),100000000])
    for _ in range(40):
        if call(rpc,"getBalance",[str(owner)])["value"]>=100000000:
            break
        time.sleep(.25)
    else:
        raise ValueError("ephemeral local fee payer not funded")
    token_program=Pubkey.from_string(TOKEN_PROGRAM)
    ata_program=Pubkey.from_string(ATA_PROGRAM)
    def ata(mint):
        return str(Pubkey.find_program_address(
            [bytes(owner),bytes(token_program),bytes(Pubkey.from_string(mint))],
            ata_program)[0])
    account_a,account_b=ata(mint_a),ata(mint_b)
    call(rpc,"surfnet_setTokenAccount",[
        str(owner),mint_a,{"amount":amount*10,"state":"initialized"},TOKEN_PROGRAM])
    acct=call(rpc,"getAccountInfo",[account_a,{"encoding":"base64"}])["value"]
    if not acct or acct.get("owner")!=TOKEN_PROGRAM:
        raise ValueError("synthetic local input token account missing")
    token=decode_token_account(base64.b64decode(acct["data"][0],validate=True))
    if (token["mint"]!=mint_a or token["authority"]!=str(owner)
            or token["amount_base_units"]<amount):
        raise ValueError("synthetic local input token balance invalid")
    keys=[(owner,True,True),(Pubkey.from_string(account_b),False,True),
          (owner,False,False),(Pubkey.from_string(mint_b),False,False),
          (Pubkey.from_string("11111111111111111111111111111111"),False,False),
          (token_program,False,False)]
    create_output=Instruction(ata_program,bytes([1]),[
        AccountMeta(key,signer,writable) for key,signer,writable in keys])
    spacing=state["tick_spacing"]
    step=60*spacing
    start=start_tick(state["tick_current"],spacing)
    current=tick_array_pda(pool,start)
    backward=tick_array_pda(pool,start-step)
    forward=tick_array_pda(pool,start+step)
    leg_a=build(pool,state,str(owner),account_a,account_b,amount,1,
                [current,backward],input_is_token_0=True)
    leg_b=build(pool,state,str(owner),account_b,account_a,intermediate,1,
                [current,forward],input_is_token_0=False)
    signed=sign_atomic(rpc,wallet,[leg_a,leg_b],[create_output])
    report={"pool":pool,"status":"SIMULATION_UNAVAILABLE",
            "input_base_units":amount,
            "first_leg_expected_intermediate_base_units":intermediate,
            "second_leg_expected_final_base_units":quote_b["estimated_output_base_units"],
            "signed":True,"local_only":True,"mainnet_broadcast":False,
            "atomic_cycle_simulated":False,"confirmed_profitable":False}
    try:
        result=verify_atomic_cycle(rpc,signed["wire"],[
            {"address":account_a,"mint":mint_a,
             "before":token["amount_base_units"]},
            {"address":account_b,"mint":mint_b,"before":0}],
            signed["venue_programs"],5000 if mint_a=="So11111111111111111111111111111111111111112" else None)
        report.update({"status":"SIGNED_ATOMIC_ROUND_TRIP_SIMULATED",
                       "atomic_cycle_simulated":True,"balance_evidence":result})
    except (ValueError,KeyError,TypeError) as exc:
        report["failure_reason"]=str(exc)[:500]
    return report


def main():
    with open("arb/pool_registry.json") as file:
        pool=next(p["address"] for p in json.load(file)["pools"]
                  if p["venue"]=="raydium_clmm")
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    outcomes=[]
    for amount in (10000,100000,1000000):
        try:
            outcomes.append(probe(rpc,pool,amount))
        except (ValueError,KeyError,TypeError) as exc:
            outcomes.append({"input_base_units":amount,
                             "status":"ROUND_TRIP_UNAVAILABLE",
                             "failure_reason":str(exc)[:500],
                             "atomic_cycle_simulated":False,
                             "confirmed_profitable":False})
    report={"pool":pool,"attempted_sizes":len(outcomes),
            "atomic_cycles_simulated":sum(
                x.get("atomic_cycle_simulated") is True for x in outcomes),
            "negative_gross_cycles":sum(
                x.get("atomic_cycle_simulated") is True and
                x["balance_evidence"]["gross_start_token_base_units"]<0
                for x in outcomes),
            "zero_or_positive_gross_cycles":sum(
                x.get("atomic_cycle_simulated") is True and
                x["balance_evidence"]["gross_start_token_base_units"]>=0
                for x in outcomes),
            "results":outcomes,"confirmed_profitable":False,
            "mainnet_broadcast":False}
    print(json.dumps(report,indent=2))
    if os.environ.get("ATOMIC_CLMM_PROBE_REPORT"):
        with open(os.environ["ATOMIC_CLMM_PROBE_REPORT"],"w") as file:
            json.dump(report,file,indent=2)


if __name__=="__main__":
    main()
