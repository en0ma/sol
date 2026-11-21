import unittest
from unittest.mock import patch
import base64
from arb.raydium_amm_v4_preflight import authenticate_swap_market,PROGRAM
from arb.orca_whirlpool import b58

class AmmV4MarketRoleValidation(unittest.TestCase):
    def test_rejects_non_legacy_market_padding(self):
        state={"market_id":"market","market_program":"program"}
        with patch("arb.raydium_amm_v4_preflight.call",return_value={"value":{
            "owner":"program","executable":False,
            "data":[base64.b64encode(b"x"*400).decode(),"base64"]}}):
            with self.assertRaisesRegex(ValueError,"padding"):
                authenticate_swap_market("http://127.0.0.1:8899","pool",state)
    def test_rejects_wrong_source_market_owner(self):
        with patch("arb.raydium_amm_v4_preflight.call",return_value={"value":{
            "owner":"wrong","executable":False,
            "data":[base64.b64encode(b"x"*400).decode(),"base64"]}}):
            with self.assertRaisesRegex(ValueError,"wrong owner"):
                authenticate_swap_market("http://127.0.0.1:8899","pool",{
                    "market_id":"market","market_program":"program"})
if __name__=="__main__":unittest.main()
