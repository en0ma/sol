"""Real Surfpool fork preflight for PumpSwap program and authenticated config.

Exits nonzero for missing or mismatched accounts. No transaction broadcast.
Does not claim a swap was simulated.
"""
import json
import os
from arb.rpc import call
from arb.pumpswap_fee_account import fetch as fetch_fee
from arb.pumpswap_global_config import fetch as fetch_global
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_local_simulation import local_rpc_only


def run(rpc):
    local_rpc_only(rpc)
    fee=fetch_fee(rpc)
    global_config=fetch_global(rpc)
    program=call(rpc,"getAccountInfo",[PROGRAM,{"encoding":"base64"}]).get("value")
    if (not program or program.get("executable") is not True):
        raise ValueError("PumpSwap program is not executable on fork")
    if (type(fee.get("slot")) is not int or type(global_config.get("slot")) is not int):
        raise ValueError("no authenticated PumpSwap config slots")
    if not fee.get("account_authenticated"):
        raise ValueError("unverified PumpSwap FeeConfig")
    return {"status":"CONFIG_AUTHENTICATED_NOT_SWAP_VERIFIED",
            "fee_config_address":fee["address"],
            "fee_config_slot":fee["slot"],
            "global_config_slot":global_config["slot"],
            "program_executable":True,
            "simulation_verified":False,"executable_quote":False,
            "profitable_arbitrage_verified":False}


def main():
    rpc=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899")
    report=run(rpc)
    print(json.dumps(report,indent=2))
    path=os.environ.get("PUMPSWAP_PREFLIGHT_REPORT")
    if path:
        with open(path,"w") as out:
            json.dump(report,out,indent=2)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
