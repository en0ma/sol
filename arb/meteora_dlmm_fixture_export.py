"""Export authenticated Meteora DLMM accounts and executable, read-only.

Fixture remains simulation-only and must be hydrated on separate explicit
offline Surfpool. No airdrops, transactions, surfnet writes or broadcasting.
"""
import base64
import json
import os
from pathlib import Path
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.meteora_dlmm import PROGRAM, decode
from arb.meteora_dlmm_bin_preflight import check_active_bin_array
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_isolated_offline_execution import fetch_accounts
from arb.orca_three_hop_fixture_export import LOADER

MAX_ACCOUNTS=16

def export_dlmm_fixture(rpc,preflight,output):
    require_loopback_rpc(rpc)
    if preflight.get("status")!="ACTIVE_BIN_ARRAY_AUTHENTICATED":
        raise ValueError("authenticated active bin preflight required")
    pool=preflight["pool"]
    if preflight.get("oracle_evidence",{}).get("authenticated") is not True:
        raise ValueError("authenticated DLMM oracle required")
    fresh=check_active_bin_array(rpc,pool)
    if fresh.get("status")!="ACTIVE_BIN_ARRAY_AUTHENTICATED":
        raise ValueError("active DLMM array no longer authenticated")
    if preflight["active_bin_array_pda"]!=fresh["active_bin_array_pda"]:
        raise ValueError("active bin array changed between reads")
    if fresh.get("oracle_evidence",{}).get("oracle")!=preflight["oracle_evidence"]["oracle"]:
        raise ValueError("DLMM oracle changed between reads")
    state_acc=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])["value"]
    if not state_acc or state_acc.get("owner")!=PROGRAM:
        raise ValueError("DLMM pool disappeared")
    state=decode(base64.b64decode(state_acc["data"][0],validate=True))
    addresses=[PROGRAM,pool,state["reserve_x"],state["reserve_y"],
               state["token_x_mint"],state["token_y_mint"],state["oracle"]]
    for row in fresh["neighboring_bin_arrays"]:
        if row["present"] and row.get("authenticated"):
            addresses.append(row["pda"])
    addresses=list(dict.fromkeys(addresses))
    if len(addresses)>MAX_ACCOUNTS:
        raise ValueError("DLMM fixture account cap exceeded")
    accounts=fetch_accounts(rpc,addresses)
    for key in addresses:
        if not isinstance(accounts.get(key),dict):
            raise ValueError("missing authenticated DLMM fixture account: "+key)
    program=accounts[PROGRAM]
    if program.get("owner")!=LOADER or program.get("executable") is not True:
        raise ValueError("missing upgradeable DLMM program executable")
    program_raw=base64.b64decode(program["data"][0],validate=True)
    if len(program_raw)<36 or program_raw[:4]!=bytes([2,0,0,0]):
        raise ValueError("invalid DLMM upgradeable program record")
    programdata=str(Pubkey.from_bytes(program_raw[4:36]))
    pd=fetch_accounts(rpc,[programdata])[programdata]
    if not pd or pd.get("owner")!=LOADER or pd.get("executable"):
        raise ValueError("invalid DLMM programdata account")
    data=base64.b64decode(pd["data"][0],validate=True)
    if len(data)<49 or data[:4]!=bytes([3,0,0,0]) or data[45:49]!=bytes([127])+b"ELF":
        raise ValueError("DLMM programdata ELF missing")
    accounts[programdata]=pd
    payload={"source":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
             "venue":"meteora_dlmm","pool":pool,"pool_state":state,
             "preflight":fresh,"accounts":accounts,
             "fixture_hydrated":False,"signed_simulation_completed":False,
             "actionable":False,"broadcast":False,"live_execution_approved":False}
    Path(output).write_text(json.dumps(payload))
    return {"status":"READ_ONLY_DLMM_FIXTURE_EXPORTED",
            "pool":pool,"account_count":len(accounts),
            "programdata_elf_bytes":len(data)-45,
            "signed_simulation_completed":False,"broadcast":False}

def main():
    preflight=json.loads(Path(os.environ["TOKEN_DLMM_BIN_PREFLIGHT_REPORT"]).read_text())
    report=export_dlmm_fixture(
        os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
        preflight,os.environ["TOKEN_DLMM_FIXTURE_EXPORT_PATH"])
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
