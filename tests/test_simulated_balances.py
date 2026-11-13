import base64
import unittest
from arb.whirlpool_simulation import extract_balances
from arb.orca_whirlpool import SOL, USDC
from arb.token_vaults import TOKEN_PROGRAM

def token_account(mint_bytes, amount):
    raw=bytearray(165)
    raw[:32]=mint_bytes
    raw[64:72]=amount.to_bytes(8,"little")
    raw[108]=1
    return {"owner":TOKEN_PROGRAM,"data":[base64.b64encode(raw).decode(),"base64"]}

# Known base58 mint bytes via solders unavailable in offline test:
from arb.orca_whirlpool import b58
MINT_A=bytes([1])*32
MINT_B=bytes([2])*32
state={"token_mint_a":b58(MINT_A),"token_mint_b":b58(MINT_B)}

class SimulatedBalanceTests(unittest.TestCase):
    def test_real_input_debit_and_output_credit(self):
        v={"accounts":[token_account(MINT_A,0),token_account(MINT_B,25)]}
        result=extract_balances(v,"a","b",state,1000,True)
        self.assertEqual(result["spent_base_units"],1000)
        self.assertEqual(result["received_base_units"],25)

    def test_no_received_output_is_not_success(self):
        v={"accounts":[token_account(MINT_A,0),token_account(MINT_B,0)]}
        with self.assertRaises(ValueError):extract_balances(v,"a","b",state,1000,True)

    def test_missing_post_accounts_is_not_success(self):
        with self.assertRaises(ValueError):
            extract_balances({"accounts":None},"a","b",state,1000,True)

    def test_wrong_mint_rejected(self):
        v={"accounts":[token_account(MINT_B,0),token_account(MINT_A,25)]}
        with self.assertRaises(ValueError):extract_balances(v,"a","b",state,1000,True)

    def test_reverse_direction(self):
        v={"accounts":[token_account(MINT_A,77),token_account(MINT_B,0)]}
        result=extract_balances(v,"a","b",state,1000,False)
        self.assertEqual(result["received_base_units"],77)
