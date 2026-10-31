import unittest
from unittest.mock import patch
from arb.cpmm_screen import screen_pool,screen
class CPMMScreenTests(unittest.TestCase):
    @patch("arb.cpmm_screen.read_pool_config")
    def test_config_fees_included_and_never_actionable(self,read):
        read.return_value={"trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":500,
                           "fee_verified_onchain":True,"config_address":"config"}
        p={"venue":"raydium_cpmm","verified":True,"address":"pool",
           "mints":["SOL","USDC"],"vault_base_units":[1000000,1000000]}
        r=screen_pool("rpc",p,(10000,))
        self.assertEqual(r["quotes"][0]["conservative_fee_ppm"],3000)
        self.assertFalse(r["quotes_are_executable"])
        self.assertFalse(any(q["actionable"] for q in r["quotes"]))
    def test_unverified_pool_rejected(self):
        with self.assertRaises(ValueError):
            screen_pool("rpc",{"venue":"raydium_cpmm"},(100,))
    def test_bad_budget_rejected(self):
        with self.assertRaises(ValueError):screen("rpc",[],(0,))
