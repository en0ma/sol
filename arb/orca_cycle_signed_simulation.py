"""One signed, never-broadcast, three-leg Orca cycle simulation on local Surfpool.

This is an experimental attempt, not a profitable quote. All three instructions
are in the same signed transaction. Only a local loopback RPC is permitted.
"""
import base64
import json
import os
import time
from arb.rpc import call
from arb.orca_whirlpool import SOL, fetch_pool
from arb.whirlpool_preflight import verify_oracle
from arb.whirlpool_swap import inspect_swap_requirements
from arb.whirlpool_simulation import TOKEN_SPACE
from arb.orca_cycle_assembler import assemble_orca_cycle
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

MAX_LEGS = 3
INITIAL_WSOL = 1000000
# Small, conservative exploratory intermediate amounts, NOT a chained quote.
TEST_INPUTS = (INITIAL_WSOL, 1, 1)

def simulate_cycle(rpc, route):
    require_loopback_rpc(rpc)
    from solders.keypair import Keypair
    from solders.hash import Hash
    from solders.pubkey import Pubkey
    from solders.instruction import AccountMeta, Instruction
    from solders.system_program import create_account, CreateAccountParams
    from solders.transaction import Transaction

    legs, tokens = route["legs"], route["tokens"]
    if len(legs) != MAX_LEGS or len(tokens) != MAX_LEGS + 1 or tokens[0] != SOL or tokens[-1] != SOL:
        raise ValueError("expected exactly three SOL-anchored legs")
    if len(set(tokens[:-1])) != MAX_LEGS or any(l["venue"] != "orca" for l in legs):
        raise ValueError("unsupported or repeated intermediate token")
    states, oracles = {}, {}
    for leg in legs:
        state = fetch_pool(rpc, leg["pool"])
        source, target = leg["from"], leg["to"]
        if {source,target} != {state["token_mint_a"],state["token_mint_b"]}:
            raise ValueError("pool mints inconsistent with route")
        direction = "a_to_b" if source == state["token_mint_a"] else "b_to_a"
        ready = inspect_swap_requirements(rpc, leg["pool"])["directions"][direction]["available"]
        if not ready:
            return {"status":"BLOCKED_TICKS", "signed_simulation_requested":False,
                    "broadcast":False,"actionable":False}
        oracles[leg["pool"]] = verify_oracle(
            rpc, leg["pool"], adaptive_fee=state["tick_spacing"] != state["fee_tier_index_seed"])
        states[leg["pool"]] = state

    payer = Keypair()
    accounts = {mint:Keypair() for mint in tokens[:-1]}
    result = {"status":"SIMULATION_NOT_COMPLETED","broadcast":False,
              "actionable":False,"live_execution_approved":False,
              "signed_simulation_requested":False}
    # Surfpool-local test funding only; never sendTransaction.
    call(rpc,"requestAirdrop",[str(payer.pubkey()),1000000000])
    for _ in range(40):
        if call(rpc,"getBalance",[str(payer.pubkey())])["value"] >= 1000000000:
            break
        time.sleep(.25)
    else:
        raise ValueError("local ephemeral payer funding unavailable")
    rent = call(rpc,"getMinimumBalanceForRentExemption",[TOKEN_SPACE])
    setup = []
    for mint in tokens[:-1]:
        acct = accounts[mint]
        setup.append(create_account(CreateAccountParams(
            from_pubkey=payer.pubkey(),to_pubkey=acct.pubkey(),
            lamports=rent+(INITIAL_WSOL if mint==SOL else 0),
            space=TOKEN_SPACE,owner=Pubkey.from_string(TOKEN_PROGRAM))))
        setup.append(Instruction(Pubkey.from_string(TOKEN_PROGRAM),
            bytes([18])+bytes(payer.pubkey()),
            [AccountMeta(acct.pubkey(),False,True),
             AccountMeta(Pubkey.from_string(mint),False,False)]))
        if mint==SOL:
            setup.append(Instruction(Pubkey.from_string(TOKEN_PROGRAM),bytes([17]),
                [AccountMeta(acct.pubkey(),False,True)]))
    swaps = assemble_orca_cycle(
        route,states,oracles,{mint:str(key.pubkey()) for mint,key in accounts.items()},
        str(payer.pubkey()),list(TEST_INPUTS),[1,1,1])
    bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(
        setup+swaps,payer.pubkey(),[payer,*accounts.values()],Hash.from_string(bh))
    encoded=base64.b64encode(bytes(tx)).decode()
    ephemeral_addresses=[str(accounts[m].pubkey()) for m in tokens[:-1]]
    def assert_accounts_absent():
        found=call(rpc,"getMultipleAccounts",[ephemeral_addresses,{"encoding":"base64"}])
        values=found.get("value")
        if not isinstance(values,list) or len(values)!=3 or any(v is not None for v in values):
            raise ValueError("ephemeral accounts persisted or could not be checked")
    assert_accounts_absent()
    response=call(rpc,"simulateTransaction",[encoded,{
        "encoding":"base64","sigVerify":True,"commitment":"processed",
        "accounts":{"encoding":"base64","addresses":[str(accounts[m].pubkey()) for m in tokens[:-1]]}}])
    assert_accounts_absent()
    result["simulation_did_not_persist"]=True
    value=response["value"]
    result["signed_simulation_requested"]=True
    result["simulation_error"]=value.get("err")
    result["logs_tail"]=(value.get("logs") or [])[-12:]
    result["units_consumed"]=value.get("unitsConsumed")
    if value.get("err") is not None:
        result["status"]="ATOMIC_SIMULATION_FAILED"
        return result
    data=value.get("accounts")
    if not isinstance(data,list) or len(data)!=3:
        raise ValueError("post-transaction token balances absent")
    balances={}
    for mint, info in zip(tokens[:-1],data):
        if not info or info.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("missing token account in simulation result")
        decoded=decode_token_account(base64.b64decode(info["data"][0],validate=True))
        if decoded["mint"]!=mint or decoded["authority"]!=str(payer.pubkey()):
            raise ValueError("post simulation token mint or authority mismatch")
        balances[mint]=decoded["amount_base_units"]
    result["final_balances_base_units"]=balances
    if any(balances[m]!=0 for m in tokens[1:-1]):
        result["status"]="RESIDUAL_INTERMEDIATE_TOKENS"
        return result
    result["net_wsol_lamports_before_fees"]=balances[SOL]-INITIAL_WSOL
    result["status"]="ATOMIC_SWAP_SIMULATED_NOT_PROFIT_VALIDATED"
    return result

def main():
    with open(os.environ["TOKEN_CYCLE_TICK_PREFLIGHT_REPORT"]) as f:
        candidates=json.load(f)
    matching=[c for c in candidates["routes"] if len(c["legs"])==3
              and c["tokens"][0]==SOL and c["tokens"][-1]==SOL
              and c["all_directional_tick_arrays_ready"]]
    report={"status":"NO_READY_THREE_HOP_CYCLE","broadcast":False,
            "actionable":False,"live_execution_approved":False}
    if matching:
        try:
            report=simulate_cycle(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                                  matching[0])
        except (ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
            report={"status":"SIMULATION_BLOCKED","reason":str(exc)[:400],
                    "broadcast":False,"actionable":False,"live_execution_approved":False}
    with open(os.environ["TOKEN_CYCLE_SIGNED_SIM_REPORT"],"w") as f:
        json.dump(report,f,indent=2)
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
