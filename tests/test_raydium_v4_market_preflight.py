"""Raydium AMM v4 pool/market authentication negative controls.

Malformed OpenBook market data must fail before a builder can be admitted.
"""
import base64
import unittest
from unittest.mock import patch
from arb.orca_whirlpool import b58
from arb.eight_venue_onchain_probe import verify_legacy

def key(n):
    return b58(bytes([n])*32)

class RaydiumV4MarketPreflightTests(unittest.TestCase):
    def test_reject_market_owner_mismatch(self):
        program="675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"
        state={"base_vault":key(1),"quote_vault":key(2),
               "base_mint":key(3),"quote_mint":key(4),
               "market_id":key(5),"market_program":key(6)}
        def account(owner,data):
            return {"owner":owner,"executable":False,
                    "data":[base64.b64encode(data).decode(),"base64"]}
        pool=account(program,b"pool-data")
        vault=account("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",b"vault-data")
        market=account(key(7),b"serum"+bytes(300))
        rpc_responses=[
            {"context":{"slot":100},"value":[pool]},
            {"context":{"slot":101},"value":[pool,vault,vault,market]}]
        with patch("arb.eight_venue_onchain_probe.call",side_effect=rpc_responses):
            with patch("arb.raydium_amm_v4.decode",return_value=state):
                with patch("arb.eight_venue_onchain_probe.decode_token_account",
                           side_effect=[
                               {"mint":key(3),"authority":key(8),"amount_base_units":100},
                               {"mint":key(4),"authority":key(8),"amount_base_units":200}]):
                    with self.assertRaisesRegex(ValueError,"market owner mismatch"):
                        verify_legacy("http://127.0.0.1:8899","raydium_amm_v4",key(9))
