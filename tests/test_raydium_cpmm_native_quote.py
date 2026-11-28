import base64
import unittest
from unittest.mock import patch
from hashlib import sha256
from arb.raydium_cpmm_native_quote import (
    decode_amm_config, quote_cpmm_exact_input, CONFIG_DISC, CONFIG_LEN)
from arb.raydium_cpmm import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM

A="a"*44
B="b"*44
POOL="p"*44
CFG="c"*44
def config_raw(trade=2500,creator=0):
    raw=bytearray(CONFIG_LEN)
    raw[:8]=CONFIG_DISC
    raw[12:20]=trade.to_bytes(8,"little")
    raw[20:28]=(120000).to_bytes(8,"little")
    raw[28:36]=(40000).to_bytes(8,"little")
    raw[108:116]=creator.to_bytes(8,"little")
    return bytes(raw)

class CPMMNativeQuoteTests(unittest.TestCase):
    def test_onchain_config_fee_decoder_and_rejections(self):
        self.assertEqual(decode_amm_config(config_raw())["trade_fee_rate"],2500)
        with self.assertRaises(ValueError):decode_amm_config(b"x"*CONFIG_LEN)
        with self.assertRaises(ValueError):decode_amm_config(config_raw(trade=1000000))
    def test_verified_accounts_in_same_slot_generate_exact_integer_quote(self):
        state={"swap_enabled":True,"token_0_program":TOKEN_PROGRAM,
               "token_1_program":TOKEN_PROGRAM,"token_0_mint":A,
               "token_1_mint":B,"token_0_vault":"v"*44,
               "token_1_vault":"w"*44,"amm_config":CFG,
               "enable_creator_fee":False,"creator_fee_on":0,
               "protocol_fees_token_0":50,"fund_fees_token_0":0,
               "creator_fees_token_0":0,
               "protocol_fees_token_1":0,"fund_fees_token_1":0,
               "creator_fees_token_1":0}
        def acc(raw,owner):
            return {"owner":owner,"executable":False,
                    "data":[base64.b64encode(raw).decode(),"base64"]}
        accounts=[acc(b"pool",PROGRAM),acc(b"vault0",TOKEN_PROGRAM),
                  acc(b"vault1",TOKEN_PROGRAM),acc(config_raw(),PROGRAM)]
        def rpc(_rpc,method,_params):
            if method=="getAccountInfo":return {"value":accounts[0]}
            if method=="getMultipleAccounts":return {"context":{"slot":555},
                                                        "value":accounts}
            raise AssertionError(method)
        tokens=[{"mint":A,"authority":POOL,"amount_base_units":1050},
                {"mint":B,"authority":POOL,"amount_base_units":1000}]
        with patch("arb.raydium_cpmm_native_quote.call",side_effect=rpc),\
             patch("arb.raydium_cpmm_native_quote.decode",return_value=state),\
             patch("arb.raydium_cpmm_native_quote.decode_token_account",
                   side_effect=tokens):
            r=quote_cpmm_exact_input("http://127.0.0.1:8899",POOL,A,100)
        # Effective curve reserves 1000/1000, ceil(100*.0025)=1,
        # x*y curve floor: 99*1000//(1000+99)=90.
        self.assertEqual(r["amount_out_base_units"],90)
        self.assertEqual(r["swap_fee_input_base_units"],1)
        self.assertEqual(r["source_slot"],555)
        self.assertFalse(r["signed_native_parity_verified"])
        self.assertFalse(r["net_profitability_verified"])

if __name__=="__main__":unittest.main()
