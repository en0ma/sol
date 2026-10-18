"""Dependency-free Solana JSON-RPC with bounded 429 retries and jitter."""
import json
import os
import fcntl
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
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

def _retry_after(error):
    """HTTP Retry-After delta-seconds or HTTP-date; ignore malformed values."""
    if not isinstance(error, HTTPError):
        return None
    header = error.headers.get("Retry-After") if error.headers else None
    if not header:
        return None
    try:
        seconds = float(header)
        if seconds >= 0 and seconds != float("inf"):
            return seconds
    except (ValueError, TypeError):
        try:
            target = parsedate_to_datetime(header)
            if target.tzinfo is None:
                return None
            return max(0.0, (target - datetime.now(timezone.utc)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            pass
    return None

def _pace_request():
    """Optional cross-process RPC pacing. Disabled unless configured in CI."""
    value=os.environ.get("SOLANA_RPC_MIN_INTERVAL_SECONDS")
    if value is None:
        return
    try:
        interval=float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError("invalid RPC pacing interval") from exc
    if not 0 < interval <= 10:
        raise ValueError("invalid RPC pacing interval")
    path=os.environ.get("SOLANA_RPC_PACING_FILE","/tmp/solana-rpc-last-request")
    with open(path,"a+") as state:
        fcntl.flock(state,fcntl.LOCK_EX)
        try:
            state.seek(0)
            try:
                last=float(state.read().strip())
            except ValueError:
                last=0.0
            now=time.monotonic()
            remaining=last+interval-now
            if remaining>0:
                time.sleep(remaining)
            state.seek(0)
            state.truncate()
            state.write(str(time.monotonic()))
            state.flush()
        finally:
            fcntl.flock(state,fcntl.LOCK_UN)

def call(url, method, params=None, timeout=20, retries=3, base_delay=0.35, max_delay=3.0):
    """Retry ONLY throttling with capped exponential full jitter; fail closed."""
    if not isinstance(retries, int) or not 0 <= retries <= 6:
        raise ValueError("invalid retry bound")
    if not (0 < base_delay <= max_delay <= 15):
        raise ValueError("invalid backoff settings")
    if os.environ.get("SOLANA_RPC_ALCHEMY_FREE_TIER")=="1":
        retries=max(retries,6)
        base_delay=max(base_delay,1.0)
        max_delay=max(max_delay,10.0)
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": [] if params is None else params}).encode()
    for attempt in range(retries + 1):
        try:
            _pace_request()
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
            minimum = _retry_after(exc)
            # Never retry earlier than Retry-After, but keep total sleep bounded.
            # A server asking for a longer wait than the budget fails closed.
            if minimum is not None and minimum > max_delay:
                raise RPCError("RPC rate limit Retry-After exceeds backoff budget") from exc
            time.sleep(max(minimum or 0.0, random.uniform(0, delay)))
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
