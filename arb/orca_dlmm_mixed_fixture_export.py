"""Read-only authenticated two-leg Orca/Meteora fixture export.

Accepts only a fully on-chain-verified SOL/USDC closed route with exactly one
Orca Whirlpool and one Meteora DLMM leg. No upstream writes or execution.
"""
import base64
import json
import os
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_whirlpool import SOL,USDC,PROGRAM as ORCA,fetch_pool
from arb.meteora_dlmm import PROGRAM as DLMM,decode as decode_dlmm
from arb.whirlpool_swap import select_tick_arrays
from arb.whirlpool_preflight import verify_oracle,oracle_address
from arb.meteora_dlmm_bin_preflight import check_active_bin_array
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_isolated_offline_execution import fetch_accounts
from arb.orca_three_hop_fixture_export import LOADER

MAX_ACCOUNTS=32

def require_route(route):
    legs=route.get("legs",[])
    tokens=route.get("tokens",[])
    if (len(legs)!=2 or len(tokens)!=3 or tokens[0] not in (SOL,USDC)
            or tokens[-1]!=tokens[0]
            or {l.get("venue") for l in legs}!={"orca","meteora_dlmm"}
            or any(l.get("from")!=tokens[i] or l.get("to")!=tokens[i+1]
                   for i,l in enumerate(legs))):
        raise ValueError("only verified closed Orca/Meteora two-leg cycle supported")
    if legs[0]["pool"]==legs[1]["pool"]:
        raise ValueError("reused pool prohibited")

def export_mixed(rpc,readiness,output):
    require_loopback_rpc(rpc)
    route=readiness.get("first_dlmm_only_offline_target")
    if not isinstance(route,dict):
        raise ValueError("no verified mixed target")
    require_route(route)
    addresses=[ORCA,DLMM]
    optional_oracles=set()
    leg_evidence={}
    for leg in route["legs"]:
        pool=leg["pool"]
        source,target=leg["from"],leg["to"]
        if leg["venue"]=="orca":
            state=fetch_pool(rpc,pool)
            a,b=state["token_mint_a"],state["token_mint_b"]
            if (source,target) not in ((a,b),(b,a)):
                raise ValueError("Orca mint identity mismatch")
            oracle=verify_oracle(rpc,pool,
                adaptive_fee=state["tick_spacing"]!=state["fee_tier_index_seed"])
            optional_oracles.add(oracle)
            arrays=select_tick_arrays(pool,state["tick_current_index"],
                                      state["tick_spacing"],source==a)
            addresses += [pool,state["token_vault_a"],state["token_vault_b"],
                          a,b,oracle,*arrays]
            leg_evidence[pool]={"venue":"orca","oracle":oracle,"tick_arrays":arrays}
        else:
            bin_report=check_active_bin_array(rpc,pool)
            if bin_report["status"]!="ACTIVE_BIN_ARRAY_AUTHENTICATED":
                raise ValueError("DLMM active bins not authenticated")
            pool_account=call(rpc,"getAccountInfo",[pool,{"encoding":"base64"}])["value"]
            if not pool_account or pool_account["owner"]!=DLMM:
                raise ValueError("DLMM pool missing")
            state=decode_dlmm(base64.b64decode(pool_account["data"][0],validate=True))
            x,y=state["token_x_mint"],state["token_y_mint"]
            if (source,target) not in ((x,y),(y,x)):
                raise ValueError("DLMM mint identity mismatch")
            addresses += [pool,state["reserve_x"],state["reserve_y"],
                          x,y,state["oracle"]]
            arrays=[item["pda"] for item in bin_report["neighboring_bin_arrays"]
                    if item.get("authenticated")]
            addresses += arrays
            leg_evidence[pool]={"venue":"meteora_dlmm","preflight":bin_report,
                                "authenticated_bin_arrays":arrays}
    addresses=list(dict.fromkeys(addresses))
    if len(addresses)>MAX_ACCOUNTS:
        raise ValueError("mixed fixture account cap exceeded")
    accounts=fetch_accounts(rpc,addresses)
    for address in addresses:
        info=accounts.get(address)
        if info is None and address in optional_oracles:
            continue
        if not isinstance(info,dict):
            raise ValueError("missing authenticated mixed account: "+address)
    for program in (ORCA,DLMM):
        info=accounts[program]
        if info.get("owner")!=LOADER or info.get("executable") is not True:
            raise ValueError("invalid upgradeable venue executable")
        raw=base64.b64decode(info["data"][0],validate=True)
        if len(raw)<36 or raw[:4]!=bytes([2,0,0,0]):
            raise ValueError("invalid upgradeable program header")
        address=str(Pubkey.from_bytes(raw[4:36]))
        pd=fetch_accounts(rpc,[address])[address]
        if not pd or pd.get("owner")!=LOADER or pd.get("executable"):
            raise ValueError("invalid venue ProgramData account")
        pd_raw=base64.b64decode(pd["data"][0],validate=True)
        if len(pd_raw)<49 or pd_raw[:4]!=bytes([3,0,0,0]) or pd_raw[45:49]!=bytes([127])+b"ELF":
            raise ValueError("missing venue ELF header")
        accounts[address]=pd
    payload={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
             "route":route,"leg_evidence":leg_evidence,"accounts":accounts,
             "signed_atomic_simulation_verified":False,
             "actionable":False,"live_execution_approved":False,"broadcast":False}
    Path(output).write_text(json.dumps(payload))
    return {"status":"READ_ONLY_ORCA_DLMM_MIXED_FIXTURE_EXPORTED",
            "pool_count":2,"account_count":len(accounts),
            "signed_atomic_simulation_verified":False,"broadcast":False}

def main():
    readiness=json.loads(Path(os.environ["TOKEN_MIXED_READINESS_REPORT"]).read_text())
    report=export_mixed(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                        readiness,os.environ["TOKEN_MIXED_FIXTURE_EXPORT_PATH"])
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
