"""Read-only export of an authenticated three-hop Orca fixture.

No account writes on the upstream-backed fork. The resulting fixture can be
hydrated only by a separate, explicitly offline procedure.
"""
import base64
import json
import os
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_whirlpool import SOL, PROGRAM, fetch_pool
from arb.whirlpool_swap import select_tick_arrays
from arb.whirlpool_preflight import verify_oracle
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_isolated_offline_execution import fetch_accounts

LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
MAX_FIXTURE_ACCOUNTS = 45
MAX_DISTINCT_ROUTES = 3

def export_cycle(rpc, preflight, output, route_index=0):
    require_loopback_rpc(rpc)
    eligible = [r for r in preflight.get("routes", [])
                if r.get("all_directional_tick_arrays_ready")
                and len(r.get("legs", [])) == 3
                and r.get("tokens", [None])[0] == SOL
                and r["tokens"][-1] == SOL]
    if not eligible:
        return {"status": "NO_VERIFIED_THREE_HOP_ORCA_FIXTURE", "broadcast": False}
    if not 0 <= route_index < len(eligible):
        raise ValueError("route index outside verified fixture candidates")
    route = eligible[route_index]
    accounts_to_read = [PROGRAM]
    optional_oracles = set()
    for i, leg in enumerate(route["legs"]):
        if leg["venue"] != "orca" or leg["from"] != route["tokens"][i] or leg["to"] != route["tokens"][i+1]:
            raise ValueError("unverified disconnected or non-Orca route")
        state = fetch_pool(rpc, leg["pool"])
        a, b = state["token_mint_a"], state["token_mint_b"]
        if (leg["from"], leg["to"]) == (a, b):
            a_to_b = True
        elif (leg["from"], leg["to"]) == (b, a):
            a_to_b = False
        else:
            raise ValueError("onchain mint mismatch")
        oracle = verify_oracle(rpc, leg["pool"],
             adaptive_fee=state["tick_spacing"] != state["fee_tier_index_seed"])
        optional_oracles.add(oracle)
        accounts_to_read.extend([leg["pool"],state["token_vault_a"],
                                 state["token_vault_b"],a,b,oracle])
        accounts_to_read.extend(select_tick_arrays(
            leg["pool"],state["tick_current_index"],state["tick_spacing"],a_to_b))
    accounts_to_read = list(dict.fromkeys(accounts_to_read))
    if len(accounts_to_read) > MAX_FIXTURE_ACCOUNTS:
        raise ValueError("three-hop fixture exceeds bounded account list")
    accounts = fetch_accounts(rpc, accounts_to_read)
    for address in accounts_to_read:
        info = accounts.get(address)
        # An absent non-adaptive oracle PDA is explicitly allowed by Orca.
        if info is None and address in optional_oracles:
            continue
        if not isinstance(info, dict):
            raise ValueError("missing verified fixture account: " + address)
    executable = accounts[PROGRAM]
    if executable.get("owner") != LOADER or executable.get("executable") is not True:
        raise ValueError("authentic upgradeable Whirlpool executable missing")
    raw = base64.b64decode(executable["data"][0], validate=True)
    if len(raw) < 36 or raw[:4] != bytes([2,0,0,0]):
        raise ValueError("unexpected Whirlpool program format")
    programdata_key = str(Pubkey.from_bytes(raw[4:36]))
    accounts.update(fetch_accounts(rpc, [programdata_key]))
    pd = accounts.get(programdata_key)
    if not isinstance(pd, dict) or pd.get("owner") != LOADER:
        raise ValueError("missing authenticated Whirlpool programdata")
    program_bytes = base64.b64decode(pd["data"][0], validate=True)
    if len(program_bytes) < 49 or program_bytes[:4] != bytes([3,0,0,0]) or program_bytes[45:49] != bytes([127])+b"ELF":
        raise ValueError("Whirlpool programdata lacks expected ELF")
    payload = {"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
               "route":route,"accounts":accounts,
               "fixture_hydrated":False,"signed_simulation_completed":False,
               "actionable":False,"live_execution_approved":False,"broadcast":False}
    Path(output).write_text(json.dumps(payload))
    return {"status":"READ_ONLY_THREE_HOP_FIXTURE_EXPORTED",
            "account_count":len(accounts),"route":route["tokens"],
            "fixture_hydrated":False,"broadcast":False}

def main():
    with open(os.environ["TOKEN_CYCLE_TICK_PREFLIGHT_REPORT"]) as stream:
        ready=json.load(stream)
    target=os.environ["TOKEN_CYCLE_FIXTURE_EXPORT_REPORT"]
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    eligible=[r for r in ready.get("routes",[]) if r.get("all_directional_tick_arrays_ready")
              and len(r.get("legs",[]))==3 and r.get("tokens",[None])[0]==SOL
              and r["tokens"][-1]==SOL]
    selected=[]
    distinct=set()
    pool_sets=set()
    # Distinct directed paths are economically different even when reversing\n    # the same three pools; report pool-set diversity separately.
    for i,route in enumerate(eligible):
        key=tuple((leg["pool"],leg["from"],leg["to"]) for leg in route["legs"])
        if key in distinct:
            continue
        distinct.add(key)
        pool_sets.add(frozenset(leg["pool"] for leg in route["legs"]))
        selected.append(i)
        if len(selected)>=MAX_DISTINCT_ROUTES:
            break
    reports=[]
    for number,index in enumerate(selected):
        destination=target if number==0 else target.removesuffix(".json")+"-"+str(number)+".json"
        try:
            reports.append(export_cycle(rpc,ready,destination,route_index=index))
        except (ValueError,KeyError,TypeError,OSError,TimeoutError) as exc:
            reports.append({"status":"THREE_HOP_EXPORT_BLOCKED","route_index":index,
                            "reason":str(exc)[:240],"broadcast":False})
    print(json.dumps({"routes_selected":len(selected),
                      "unique_pool_sets_selected":len(pool_sets),
                      "distinct_directional_routes_selected":len(selected),
                      "exports":reports,
                      "broadcast":False},indent=2))

if __name__=="__main__":
    main()
