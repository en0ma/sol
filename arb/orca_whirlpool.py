"""Verified Orca Whirlpool account decoding, using only Surfpool JSON-RPC.

Layout references: orca_whirlpools_client generated Whirlpool account, 653 bytes.
Does not implement swap quote/tick-array math.
"""
import base64
import hashlib
import json
import os
from arb.rpc import call

PROGRAM = "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SIZE = 653
DISCRIMINATOR = hashlib.sha256(b"account:Whirlpool").digest()[:8]
ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58(data):
    value = int.from_bytes(data, "big")
    output = ""
    while value:
        value, digit = divmod(value, 58)
        output = ALPHABET[digit] + output
    return "1" * (len(data) - len(data.lstrip(b"\\x00"))) + output

def decode(raw):
    if len(raw) != SIZE or raw[:8] != DISCRIMINATOR:
        raise ValueError("invalid Whirlpool length or discriminator")
    le = lambda start, length, signed=False: int.from_bytes(raw[start:start+length], "little", signed=signed)
    result = {
        "tick_spacing": le(41, 2),
        "fee_tier_index_seed": le(43, 2),
        "fee_rate_hundredths_bps": le(45, 2),
        "protocol_fee_rate": le(47, 2),
        "liquidity": str(le(49, 16)),
        "sqrt_price_x64": str(le(65, 16)),
        "tick_current_index": le(81, 4, True),
        "token_mint_a": b58(raw[101:133]),
        "token_vault_a": b58(raw[133:165]),
        "token_mint_b": b58(raw[181:213]),
        "token_vault_b": b58(raw[213:245]),
    }
    if result["tick_spacing"] == 0 or le(65, 16) == 0:
        raise ValueError("invalid Whirlpool price or tick spacing")
    return result

def fetch_pool(rpc, address):
    result = call(rpc, "getAccountInfo", [address, {"encoding": "base64", "commitment": "confirmed"}])
    info = result.get("value")
    if not info or info.get("owner") != PROGRAM or info.get("executable"):
        raise ValueError("missing or incorrectly owned Whirlpool")
    encoded = info.get("data")
    if not isinstance(encoded, list) or encoded[1] != "base64":
        raise ValueError("unexpected account encoding")
    decoded = decode(base64.b64decode(encoded[0], validate=True))
    return {"address": address, **decoded}

def find_pair(rpc, mint_a=SOL, mint_b=USDC, max_results=20):
    """Narrow server-side filtering; no unfiltered program-account scans."""
    if max_results < 1:
        raise ValueError("max_results must be positive")
    results = []
    for a, b in ((mint_a, mint_b), (mint_b, mint_a)):
        filters = [{"dataSize": SIZE},
                   {"memcmp": {"offset": 0, "bytes": b58(DISCRIMINATOR)}},
                   {"memcmp": {"offset": 101, "bytes": a}},
                   {"memcmp": {"offset": 181, "bytes": b}}]
        accounts = call(rpc, "getProgramAccounts", [PROGRAM, {
            "encoding": "base64", "commitment": "confirmed", "filters": filters
        }], timeout=90)
        if not isinstance(accounts, list) or len(accounts) > max_results:
            raise ValueError("unexpected/excessive Whirlpool query response")
        for entry in accounts:
            account = entry["account"]
            if account["owner"] != PROGRAM or account.get("executable"):
                raise ValueError("program account owner mismatch")
            data = account["data"]
            decoded = decode(base64.b64decode(data[0], validate=True))
            if (decoded["token_mint_a"], decoded["token_mint_b"]) != (a, b):
                raise ValueError("pool mint mismatch")
            results.append({"address": entry["pubkey"], **decoded})
    return results

if __name__ == "__main__":
    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    print(json.dumps(find_pair(rpc), indent=2))
