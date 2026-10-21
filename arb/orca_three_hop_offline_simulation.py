"""Offline-only hydration and signed, three-hop Orca cycle simulation.

Requires an authenticated read-only export and a SEPARATE Surfpool --offline
instance. Never connects to upstream, never calls sendTransaction.
"""
import base64
import json
import os
import sys
from pathlib import Path
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.transaction import Transaction
from arb.rpc import call, RPCError
from arb.orca_whirlpool import PROGRAM, SOL, fetch_pool
from arb.whirlpool_preflight import verify_oracle
from arb.orca_cycle_assembler import assemble_orca_cycle
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
SYSTEM = "11111111111111111111111111111111"
MAX_BYTES = 1232
INITIAL_WSOL = 1000000

def offline_gate(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("offline fixture writes prohibited without explicit offline opt-in")

def quote_hops_offline(rpc, route, states, oracles, user_accounts, signer):
    """Probe exact-input quantities, funding only disposable offline token accounts.

    Each hop is simulated against its own authenticated pool snapshot. These
    probes are NOT an atomic quote: the final three-swap simulation remains
    authoritative, and residual output is fail-closed.
    """
    from arb.whirlpool_swap import build_swap
    offline_gate(rpc)
    legs, tokens = route["legs"], route["tokens"]
    amounts = []
    current_amount = INITIAL_WSOL
    probes = []
    for i, leg in enumerate(legs):
        if current_amount <= 0:
            raise ValueError("intermediate hop quote yielded zero input")
        mint = tokens[i]
        account = user_accounts[mint]
        if i:
            # This mutates only the isolated offline synthetic account.
            # Never populate an intermediate account in the final atomic
            # starting state; it must start with zero.
            call(rpc, "surfnet_setAccount", [account, {
                "lamports": 2039280,
                "data": token_account_bytes(mint, str(signer.pubkey()), current_amount).hex(),
                "owner": TOKEN_PROGRAM, "executable": False}])
        pool = leg["pool"]
        state = states[pool]
        a_to_b = mint == state["token_mint_a"]
        instruction = build_swap(pool,state,str(signer.pubkey()),
            user_accounts[state["token_mint_a"]],
            user_accounts[state["token_mint_b"]],oracles[pool],
            current_amount,1,a_to_b=a_to_b)
        bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer(
            [instruction],signer.pubkey(),[signer],Hash.from_string(bh))
        before = call(rpc,"getAccountInfo",[user_accounts[tokens[i+1]],{"encoding":"base64"}])["value"]
        initial_out = 0
        if before:
            initial_out = decode_token_account(
                base64.b64decode(before["data"][0],validate=True))["amount_base_units"]
        response=call(rpc,"simulateTransaction",[base64.b64encode(bytes(tx)).decode(),{
            "encoding":"base64","sigVerify":True,
            "accounts":{"encoding":"base64","addresses":[user_accounts[tokens[i+1]]]}}])
        value=response.get("value",{})
        if value.get("err") is not None:
            raise ValueError("hop "+str(i+1)+" quote simulation failed: "+str(value["err"]))
        after=value.get("accounts")
        if not isinstance(after,list) or len(after)!=1 or not after[0]:
            raise ValueError("missing hop output account in quote simulation")
        output=decode_token_account(
            base64.b64decode(after[0]["data"][0],validate=True))
        if output["mint"]!=tokens[i+1] or output["authority"]!=str(signer.pubkey()):
            raise ValueError("quote returned wrong token or signer")
        received=output["amount_base_units"]-initial_out
        if received<=0:
            raise ValueError("hop "+str(i+1)+" yielded no output")
        amounts.append(current_amount)
        probes.append({"hop":i+1,"input_base_units":current_amount,
                       "quoted_output_base_units":received,
                       "compute_units":value.get("unitsConsumed")})
        current_amount=received
    # Restore intermediate accounts to empty before atomic simulation.
    for mint in tokens[1:-1]:
        call(rpc,"surfnet_setAccount",[user_accounts[mint],{
            "lamports":2039280,
            "data":token_account_bytes(mint,str(signer.pubkey()),0).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    return amounts, probes

def hydrate_and_simulate(rpc, fixture):
    offline_gate(rpc)
    if fixture.get("source") != "READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("untrusted fixture provenance")
    route = fixture["route"]
    legs, tokens = route["legs"], route["tokens"]
    if len(legs) != 3 or len(tokens) != 4 or tokens[0] != SOL or tokens[-1] != SOL:
        raise ValueError("unsupported nonclosed route")
    if len(set(tokens[:3])) != 3 or len({l["pool"] for l in legs}) != 3:
        raise ValueError("repeated pool or intermediate token")
    if any(l["venue"] != "orca" or l["from"] != tokens[i] or l["to"] != tokens[i+1]
           for i,l in enumerate(legs)):
        raise ValueError("disconnected or non-Orca leg")
    accounts = fixture["accounts"]
    program = accounts[PROGRAM]
    raw = base64.b64decode(program["data"][0],validate=True)
    if program["owner"] != LOADER or not program["executable"] or raw[:4] != bytes([2,0,0,0]):
        raise ValueError("authentic upgradeable Whirlpool program missing")
    programdata_key = str(Pubkey.from_bytes(raw[4:36]))
    pd = accounts[programdata_key]
    pd_raw = base64.b64decode(pd["data"][0],validate=True)
    if pd["owner"] != LOADER or pd_raw[:4] != bytes([3,0,0,0]) or pd_raw[45:49] != bytes([127])+b"ELF":
        raise ValueError("invalid authenticated programdata")
    # All fixture state mutations are local cheatcodes on explicitly offline Surfpool.
    for address, info in accounts.items():
        if address in (PROGRAM,programdata_key):
            continue
        if info is None:
            # A non-adaptive Whirlpool oracle PDA may be absent in the
            # authenticated fork; the legacy swap leaves it unchecked.
            from arb.whirlpool_preflight import oracle_address
            known_oracles={oracle_address(leg["pool"]) for leg in legs}
            if address not in known_oracles:
                raise ValueError("missing non-oracle authenticated state: " + address)
            continue
        data = info["data"]
        if not isinstance(data,list) or data[1] != "base64":
            raise ValueError("invalid exported account")
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":info["lamports"],
            "data":base64.b64decode(data[0],validate=True).hex(),
            "owner":info["owner"],"executable":info["executable"]}])
    elf=pd_raw[45:]
    for offset in range(0,len(elf),16384):
        call(rpc,"surfnet_writeProgram",[PROGRAM,elf[offset:offset+16384].hex(),offset])
    signer=Keypair()
    user_accounts={}
    for mint in tokens[:-1]:
        mint_info=accounts.get(mint)
        if not isinstance(mint_info,dict) or mint_info["owner"] != TOKEN_PROGRAM:
            raise ValueError("unsupported non-classic SPL intermediate token: "+mint)
        address=str(Keypair().pubkey())
        amount=INITIAL_WSOL if mint==SOL else 0
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,
            "data":token_account_bytes(mint,str(signer.pubkey()),amount).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
        user_accounts[mint]=address
    call(rpc,"surfnet_setAccount",[str(signer.pubkey()),{
        "lamports":1000000000,"data":"","owner":SYSTEM,"executable":False}])
    states,oracles={},{}
    for leg in legs:
        pool=leg["pool"]
        state=fetch_pool(rpc,pool)
        if {leg["from"],leg["to"]}!={state["token_mint_a"],state["token_mint_b"]}:
            raise ValueError("hydrated pool mint mismatch")
        states[pool]=state
        oracles[pool]=verify_oracle(rpc,pool,
            adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
    try:
        quoted_amounts, quote_probes = quote_hops_offline(
            rpc,route,states,oracles,user_accounts,signer)
    except ValueError as exc:
        return {"status":"CHAINED_QUOTE_BLOCKED","reason":str(exc)[:500],
                "fixture_hydrated":True,"signed_simulation_requested":False,
                "actionable":False,"live_execution_approved":False,"broadcast":False}
    swaps=assemble_orca_cycle(route,states,oracles,user_accounts,
                              str(signer.pubkey()),quoted_amounts,[1,1,1])
    bh=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(swaps,signer.pubkey(),[signer],Hash.from_string(bh))
    wire=bytes(tx)
    result={"status":"SIMULATION_NOT_ATTEMPTED","route":tokens,
            "independent_hop_quote_probes":quote_probes,
            "transaction_bytes":len(wire),"fixture_hydrated":True,
            "signed_simulation_requested":False,"actionable":False,
            "live_execution_approved":False,"broadcast":False}
    if len(wire)>MAX_BYTES:
        result["status"]="BLOCKED_TRANSACTION_SIZE"
        return result
    user_addresses=[user_accounts[t] for t in tokens[:-1]]
    def balances():
        response=call(rpc,"getMultipleAccounts",[user_addresses,{"encoding":"base64"}])
        infos=response["value"]
        if not isinstance(infos,list) or len(infos)!=3:
            raise ValueError("missing offline account snapshot")
        amounts={}
        for mint,info in zip(tokens[:-1],infos):
            if not info or info["owner"]!=TOKEN_PROGRAM:
                raise ValueError("incorrect persistent user account owner")
            decoded=decode_token_account(base64.b64decode(info["data"][0],validate=True))
            if decoded["mint"]!=mint or decoded["authority"]!=str(signer.pubkey()):
                raise ValueError("incorrect persistent account authority")
            amounts[mint]=decoded["amount_base_units"]
        return amounts
    before=balances()
    if any(before[t]!=(INITIAL_WSOL if t==SOL else 0) for t in tokens[:-1]):
        raise ValueError("offline fixture not at exact initial balances")
    resp=call(rpc,"simulateTransaction",[base64.b64encode(wire).decode(),{
        "encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
        "accounts":{"encoding":"base64","addresses":user_addresses}}])
    after=balances()
    if after!=before:
        raise ValueError("offline simulated transaction persisted account mutations")
    result["simulation_did_not_persist"]=True
    result["signed_simulation_requested"]=True
    if "error" in resp:
        result["status"]="SIMULATION_RPC_REJECTED"
        result["rpc_error"]=str(resp["error"])[:500]
        return result
    value=resp["value"]
    result["simulation_error"]=value.get("err")
    result["units_consumed"]=value.get("unitsConsumed")
    logs=value.get("logs") or []
    result["logs_tail"]=logs[-18:]
    result["whirlpool_invocations"]=sum(("Program "+PROGRAM+" invoke") in line for line in logs)
    result["whirlpool_successes"]=sum(("Program "+PROGRAM+" success") in line for line in logs)
    if value.get("err") is not None:
        result["status"]="ATOMIC_SIMULATION_FAILED"
        return result
    if result["whirlpool_invocations"] != 3 or result["whirlpool_successes"] != 3:
        result["status"]="MISSING_THREE_SUCCESSFUL_WHIRLPOOL_INVOCATIONS"
        return result
    post=value.get("accounts")
    if not isinstance(post,list) or len(post)!=3:
        raise ValueError("missing simulated post-swap token accounts")
    final={}
    for mint,info in zip(tokens[:-1],post):
        if not info or info["owner"]!=TOKEN_PROGRAM:
            raise ValueError("invalid simulated account owner")
        decoded=decode_token_account(base64.b64decode(info["data"][0],validate=True))
        if decoded["mint"]!=mint or decoded["authority"]!=str(signer.pubkey()):
            raise ValueError("simulated account mint/authority mismatch")
        final[mint]=decoded["amount_base_units"]
    result["final_balances_base_units"]=final
    if any(final[t] for t in tokens[1:-1]):
        result["status"]="RESIDUAL_INTERMEDIATE_TOKENS"
    else:
        result["status"]="ATOMIC_SWAP_SIMULATED_NOT_PROFIT_VALIDATED"
        result["net_wsol_before_fees"]=final[SOL]-INITIAL_WSOL
    return result

def main():
    report={"status":"OFFLINE_SIMULATION_NOT_STARTED","broadcast":False,
            "actionable":False,"live_execution_approved":False}
    try:
        offline_gate(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))
        report=hydrate_and_simulate(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                                   json.loads(Path(sys.argv[1]).read_text()))
    except (RPCError,ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
        report={"status":"OFFLINE_SIMULATION_BLOCKED","reason":str(exc)[:500],
                "broadcast":False,"actionable":False,"live_execution_approved":False}
    Path(sys.argv[2]).write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
