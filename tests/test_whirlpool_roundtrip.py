import base64
import unittest
from arb.orca_whirlpool import PROGRAM,b58,SOL,USDC
from arb.token_vaults import TOKEN_PROGRAM
from arb.whirlpool_roundtrip import measure_roundtrip

def mint_bytes(mint):
    chars="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number=0
    for c in mint:number=number*58+chars.index(c)
    return number.to_bytes(32,"big")

def account(mint,amount):
    buf=bytearray(165);buf[:32]=mint_bytes(mint)
    buf[64:72]=amount.to_bytes(8,"little");buf[108]=1
    return {"owner":TOKEN_PROGRAM,"data":[base64.b64encode(buf).decode(),"base64"]}

class RoundtripTests(unittest.TestCase):
    def setUp(self):
        self.state={"token_mint_a":SOL,"token_mint_b":USDC}
        self.logs=[f"Program {PROGRAM} invoke [1]",f"Program {PROGRAM} success"]*2

    def test_both_legs_and_balances(self):
        out=measure_roundtrip({"err":None,"logs":self.logs,
             "accounts":[account(SOL,900),account(USDC,0)]},self.state,1000,1)
        self.assertEqual(out["whirlpool_invocations"],2)
        self.assertEqual(out["wsol_delta_before_network_fees"],-100)

    def test_one_swap_not_counted_as_roundtrip(self):
        with self.assertRaises(ValueError):
            measure_roundtrip({"err":None,"logs":self.logs[:2],
                "accounts":[account(SOL,900),account(USDC,3)]},self.state,1000,1)

    def test_residual_usdc_rejected(self):
        with self.assertRaisesRegex(ValueError,"not closed"):
            measure_roundtrip({"err":None,"logs":self.logs,
                "accounts":[account(SOL,900),account(USDC,3)]},self.state,1000,1)

    def test_error_rejected(self):
        with self.assertRaises(ValueError):
            measure_roundtrip({"err":"slippage","logs":self.logs},self.state,1000,1)
