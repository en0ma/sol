"""Dependency-free Solana JSON-RPC with bounded 429 retries and jitter."""
import json
import random
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class RPCError(RuntimeError):
    pass

def _throttled(error):
    if isinstance(error, HTTPError):
        return error.code in (429, 503)
    if isinstance(error, RPCError):
        msg = str(error).lower()
        return ("429" in msg or "too many requests" in msg or
                "rate limit" in msg or "rate-limit" in msg)
    return False

def call(url, method, params=None, timeout=20, retries=3, base_delay=0.35, max_delay=3.0):
    """Retry ONLY throttling with capped exponential full jitter; fail closed."""
    if not isinstance(retries, int) or not 0 <= retries <= 6:
        raise ValueError("invalid retry bound")
    if not (0 < base_delay <= max_delay <= 15):
        raise ValueError("invalid backoff settings")
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": [] if params is None else params}).encode()
    for attempt in range(retries + 1):
        try:
            request = Request(url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=timeout) as res:
                response = json.load(res)
            if "error" in response:
                raise RPCError(str(response["error"]))
            if "result" not in response:
                raise RPCError("RPC missing result")
            return response["result"]
        except (HTTPError, RPCError) as exc:
            if not _throttled(exc) or attempt == retries:
                raise
            delay = min(max_delay, base_delay * (2 ** attempt))
            time.sleep(random.uniform(0, delay))
    raise AssertionError("unreachable")

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
