import base64
import unittest
from unittest.mock import patch
from arb.next_ten_signed_atomic_offline import preflight_first_leg_output
from arb.token_vaults import TOKEN_PROGRAM

class DummyTx:
    def verify(self): pass

class Tests(unittest.TestCase):
    def test_signed_preflight_observes_actual_second_input(self):
        def account(index,value):
            from arb.orca_swap_v2_offline_provision import token_account_bytes
            from solders.pubkey import Pubkey
            mint=["So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2q1N1zybapC8G4wEGGkZwyTDt1v","So11111111111111111111111111111111111111112"][index]
            owner="11111111111111111111111111111111"
            return {"owner":TOKEN_PROGRAM,"data":[base64.b64encode(token_account_bytes(mint,owner,value)).decode(),"base64"]}
        mints=["So11111111111111111111111111111111111111112","EPjFWdd5AufqSSqeM2q1N1zybapC8G4wEGGkZwyTDt1v","So11111111111111111111111111111111111111112"]
        signer=type("Signer",(),{"pubkey":lambda self:"unused"})()
        with patch("arb.next_ten_signed_atomic_offline.call",return_value={"value":{"blockhash":"11111111111111111111111111111111"}}), \
             patch("arb.next_ten_signed_atomic_offline.Transaction.new_signed_with_payer",return_value=DummyTx()), \
             patch("arb.next_ten_signed_atomic_offline._simulate",return_value=({"err":None,"accounts":[account(0,0),account(1,42),account(2,0)],"unitsConsumed":500},100)), \
             patch("arb.next_ten_signed_atomic_offline._post",return_value=[100,0,0]):
            result=preflight_first_leg_output("http://127.0.0.1:8899",None,signer,["a","b","c"],mints,"11111111111111111111111111111111",[100,0,0])
        self.assertEqual(result["planned_second_input"],42)
        self.assertFalse(result["broadcast"])
if __name__=="__main__": unittest.main()
