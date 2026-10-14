"""Minimal dependency-free Solana JSON-RPC client and account checks."""
import json
from urllib.request import Request, urlopen

class RPCError(RuntimeError):
    pass

def call(url, method, params=None, timeout=20):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": [] if params is None else params}).encode()
    request = Request(url, data=data, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=timeout) as res:
        response = json.load(res)
    if "error" in response:
        raise RPCError(str(response["error"]))
    if "result" not in response:
        raise RPCError("RPC missing result")
    return response["result"]

def inspect_account(url, address, expected_owner=None):
    result = call(url, "getAccountInfo", [address, {"encoding": "base64", "commitment": "processed"}])
    account = result.get("value")
    if not account:
        return {"address": address, "exists": False}
    actual_owner = account["owner"]
    return {"address": address, "exists": True,
            "owner": actual_owner, "executable": account["executable"],
            "lamports": account["lamports"], "space": account.get("space"),
            "owner_matches": expected_owner is None or expected_owner == actual_owner}
