"""Read-only, bounded diagnostics for rejected PumpSwap pool/mint snapshots.

This does not validate or promote pools: arb.pool_registry remains authoritative.
"""
import argparse
import base64
import json
import os
from pathlib import Path

from arb.rpc import call
from arb.pumpswap_pool import PROGRAM, decode
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

NATIVE_WS0L_MINT = "So11111111111111111111111111111111111111112"

def _bytes(account):
    if not isinstance(account, dict) or account.get("executable") is not False:
        raise ValueError("missing or executable account")
    data = account.get("data")
    if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
        raise ValueError("unsupported account encoding")
    return base64.b64decode(data[0], validate=True)

def inspect(rpc, address):
    """One read-only pool lookup and one synchronized, confirmed snapshot."""
    pool_response = call(rpc, "getAccountInfo",
                         [address, {"encoding":"base64", "commitment":"confirmed"}])
    pool = pool_response.get("value")
    if not pool or pool.get("owner") != PROGRAM:
        return {"address":address, "status":"POOL_MISSING_OR_WRONG_OWNER"}
    try:
        state = decode(_bytes(pool))
        keys = [address, state["base_mint"], state["base_vault"], state["quote_vault"]]
        snapshot = call(rpc, "getMultipleAccounts",
                        [keys, {"encoding":"base64", "commitment":"confirmed"}])
        slot = snapshot.get("context", {}).get("slot")
        accounts = snapshot.get("value")
        if type(slot) is not int or not isinstance(accounts, list) or len(accounts) != 4:
            raise ValueError("incomplete snapshot")
        if (not isinstance(accounts[0], dict) or accounts[0].get("owner") != PROGRAM or
                decode(_bytes(accounts[0])) != state):
            raise ValueError("pool changed in snapshot")
        mint = accounts[1]
        out = {"address":address, "base_mint":state["base_mint"],
               "slot":slot, "status":"OBSERVED_NOT_VALIDATED",
               "base_mint_exists":mint is not None,
               "base_mint_owner":mint.get("owner") if mint else None}
        if mint is None:
            out["mint_observation"] = "MISSING_MINT"
        elif mint.get("owner") != TOKEN_PROGRAM:
            out["mint_observation"] = "NON_CLASSIC_TOKEN_PROGRAM"
        else:
            raw = _bytes(mint)
            out["mint_account_bytes"] = len(raw)
            if len(raw) != 82:
                out["mint_observation"] = "UNSUPPORTED_MINT_LAYOUT"
            else:
                out["base_supply"] = int.from_bytes(raw[36:44], "little")
                out["mint_initialized"] = raw[45] == 1
                out["mint_observation"] = ("UNINITIALIZED" if raw[45] != 1 else
                                           "NATIVE_WSOL_ZERO_SUPPLY" if out["base_supply"] == 0 and state["base_mint"] == NATIVE_WS0L_MINT else
                                           "ZERO_SUPPLY" if out["base_supply"] == 0 else
                                           "POSITIVE_SUPPLY")
        out["vault_owners"] = [a.get("owner") if isinstance(a,dict) else None
                               for a in accounts[2:]]
        vaults = []
        for account, expected_mint in zip(accounts[2:], (state["base_mint"], state["quote_mint"])):
            item = {"owner_is_classic_spl":isinstance(account,dict) and
                    account.get("owner") == TOKEN_PROGRAM}
            if item["owner_is_classic_spl"]:
                try:
                    token = decode_token_account(_bytes(account))
                    item["mint_matches_pool"] = token["mint"] == expected_mint
                    item["authority_matches_pool"] = token["authority"] == address
                    item["amount_base_units"] = token["amount_base_units"]
                except (ValueError, KeyError, TypeError, IndexError):
                    item["layout_supported"] = False
            vaults.append(item)
        out["vault_observations"] = vaults
        return out
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        return {"address":address, "status":"SNAPSHOT_UNSUPPORTED",
                "error_type":type(exc).__name__}

def audit(rpc, report, limit=20):
    if type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError("invalid audit budget")
    if not isinstance(report, dict):
        raise ValueError("invalid rejection report")
    rejected = report.get("rejections")
    if not isinstance(rejected, list):
        raise ValueError("missing rejected candidates")
    checked=[];seen=set()
    for item in rejected:
        if not isinstance(item,dict):
            continue
        address=item.get("address")
        if (item.get("venue") != "pumpswap" or not isinstance(address,str)
                or not 32 <= len(address) <= 44 or address in seen):
            continue
        seen.add(address)
        try:
            observation = inspect(rpc,address)
        except Exception as exc:
            observation = {"address":address, "status":"RPC_OR_SNAPSHOT_ERROR",
                           "error_type":type(exc).__name__}
        observation = {**observation, "address":address,
                       "original_rejection_reason":str(item.get("reason", "UNKNOWN"))[:200]}
        checked.append(observation)
        if len(checked) >= limit:
            break
    categories = {}
    for observation in checked:
        category = observation.get("mint_observation", observation["status"])
        categories[category] = categories.get(category, 0) + 1
    return {"source":"read_only_pumpswap_rejection_audit",
            "observed_count":len(checked), "observation_categories":categories,
            "observations":checked,
            "pool_validation_performed":False, "actionable":False,
            "simulation_verified":False, "mainnet_broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rejections",required=True)
    parser.add_argument("--limit",type=int,default=10)
    parser.add_argument("--output",default="")
    args=parser.parse_args()
    report=json.loads(Path(args.rejections).read_text())
    output=audit(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),
                 report,args.limit)
    print(json.dumps(output,indent=2))
    if args.output:
        Path(args.output).write_text(json.dumps(output,indent=2))

if __name__=="__main__":
    main()
