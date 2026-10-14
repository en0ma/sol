"""Surfpool-only Whirlpool spot-state analyzer and research gate.

IMPORTANT: Spot price is not executable size-aware swap output. No transactions,
DEX HTTP APIs, priority-fee estimates, or profit claims are made here.

Run: python3 -m arb.whirlpool_market --self-test
     python3 -m arb.whirlpool_market --manifest arb/whirlpool_pools.json
"""
import argparse
import json
import os
import unittest
from decimal import Decimal, localcontext
from unittest.mock import patch

from arb.rpc import call
from arb.whirlpool_snapshot import snapshot
from arb.orca_whirlpool import SOL, USDC

Q64 = 1 << 64
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"

def mint_decimals(rpc, addresses):
    """Fetch both SPL mint accounts in one same-slot RPC response."""
    if len(addresses) != 2 or len(set(addresses)) != 2:
        raise ValueError("two distinct mint addresses required")
    response = call(rpc, "getMultipleAccounts", [
        addresses, {"encoding": "base64", "commitment": "confirmed"}])
    import base64
    accounts = response.get("value")
    slot = response.get("context", {}).get("slot")
    if not isinstance(slot, int) or not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("invalid mint-account response")
    out = {}
    for address, account in zip(addresses, accounts):
        if not account or account.get("owner") != TOKEN_PROGRAM:
            raise ValueError("unsupported mint owner: classic SPL Token required")
        d = account.get("data")
        if not isinstance(d, list) or len(d) != 2 or d[1] != "base64":
            raise ValueError("invalid mint data encoding")
        raw = base64.b64decode(d[0], validate=True)
        if len(raw) != 82 or raw[45] != 1:
            raise ValueError("mint is malformed or uninitialized")
        out[address] = int(raw[44])
        if out[address] > 18:
            raise ValueError("unsupported mint decimals")
    return {"slot": slot, "decimals": out}

def price_from_sqrt(sqrt_price_x64, decimals_a, decimals_b, fee_rate_hundredths_bps):
    """Indicative token B per token A, adjusted for token decimals."""
    sqrt = int(sqrt_price_x64)
    if sqrt <= 0 or not 0 <= decimals_a <= 18 or not 0 <= decimals_b <= 18:
        raise ValueError("invalid price or decimals")
    if not 0 <= fee_rate_hundredths_bps < 1_000_000:
        raise ValueError("invalid fee rate")
    with localcontext() as ctx:
        ctx.prec = 70
        raw = (Decimal(sqrt) / Decimal(Q64)) ** 2
        human = raw * (Decimal(10) ** (decimals_a - decimals_b))
        fee = Decimal(fee_rate_hundredths_bps) / Decimal(1_000_000)
        return {"spot_token_b_per_a": str(human),
                "spot_token_a_per_b": str(Decimal(1) / human),
                "indicative_b_per_a_after_trade_fee": str(human * (1 - fee)),
                "trade_fee_fraction": str(fee)}

def analyze(rpc, pool_address, expected_mints=(SOL, USDC)):
    state = snapshot(rpc, pool_address)
    p = state["pool"]
    if set((p["token_mint_a"], p["token_mint_b"])) != set(expected_mints):
        raise ValueError("pool has unexpected token pair")
    if int(p["liquidity"]) <= 0:
        raise ValueError("pool has no active liquidity")
    decimals = mint_decimals(rpc, [p["token_mint_a"], p["token_mint_b"]])
    quote = price_from_sqrt(p["sqrt_price_x64"],
                            decimals["decimals"][p["token_mint_a"]],
                            decimals["decimals"][p["token_mint_b"]],
                            p["fee_rate_hundredths_bps"])
    return {"pool": pool_address, "pool_slot": state["slot"],
            "mint_slot": decimals["slot"],
            "price": quote, "liquidity": p["liquidity"],
            "vault_a_units": state["vault_a"]["amount_base_units"],
            "vault_b_units": state["vault_b"]["amount_base_units"],
            "execution_ready": False,
            "reason": "spot-price analysis only; tick-array swap simulation not implemented"}

class MarketTests(unittest.TestCase):
    def test_unit_price(self):
        p=price_from_sqrt(Q64, 6, 6, 300)
        self.assertEqual(Decimal(p["spot_token_b_per_a"]), Decimal(1))
        self.assertEqual(Decimal(p["indicative_b_per_a_after_trade_fee"]), Decimal("0.9997"))

    def test_decimal_adjustment(self):
        p=price_from_sqrt(Q64, 9, 6, 0)
        self.assertEqual(Decimal(p["spot_token_b_per_a"]), Decimal(1000))

    def test_inverse(self):
        p=price_from_sqrt(2*Q64, 6, 6, 0)
        self.assertEqual(Decimal(p["spot_token_a_per_b"]), Decimal("0.25"))

    def test_reject_fee_or_zero(self):
        with self.assertRaises(ValueError):
            price_from_sqrt(0, 6, 6, 0)
        with self.assertRaises(ValueError):
            price_from_sqrt(Q64, 6, 6, 1_000_000)

    @patch("arb.whirlpool_market.mint_decimals")
    @patch("arb.whirlpool_market.snapshot")
    def test_analyze(self, snap, mint):
        snap.return_value={"slot": 50,
            "pool":{"token_mint_a":SOL,"token_mint_b":USDC,
                    "sqrt_price_x64":str(Q64),"liquidity":"100",
                    "fee_rate_hundredths_bps":300},
            "vault_a":{"amount_base_units":100},
            "vault_b":{"amount_base_units":100}}
        mint.return_value={"slot":51,"decimals":{SOL:9,USDC:6}}
        r=analyze("http://localhost", "pool")
        self.assertFalse(r["execution_ready"])
        self.assertEqual(r["pool_slot"], 50)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rpc", default=os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))
    parser.add_argument("--manifest", default="arb/whirlpool_pools.json")
    parser.add_argument("--output")
    parser.add_argument("--self-test", action="store_true")
    args=parser.parse_args()
    if args.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(MarketTests)
        return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1
    with open(args.manifest,encoding="utf-8") as f:
        pools=json.load(f)["pools"]
    report={"status":"NOT_CONFIGURED" if not pools else "PASS", "pools":[]}
    for entry in pools:
        report["pools"].append(analyze(args.rpc,entry["address"]))
    print(json.dumps(report,indent=2))
    if args.output:
        with open(args.output,"w",encoding="utf-8") as f:
            json.dump(report,f,indent=2)
    return 0 if pools else 2

if __name__=="__main__":
    raise SystemExit(main())
