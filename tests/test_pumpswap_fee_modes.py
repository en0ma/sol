import unittest
from arb.pumpswap_fee_modes import compare_fee_modes


class PumpSwapFeeModesTests(unittest.TestCase):
    def pool(self):
        standard={"lp_fee_bps":30,"protocol_fee_bps":20,"creator_fee_bps":5}
        other={"lp_fee_bps":15,"protocol_fee_bps":10,"creator_fee_bps":5}
        return {"canonical_pool_verified":True,"canonical":True,
            "base_mint_supply":1000,"base_reserve":1000,
            "quote_vault_balance":2000,"virtual_quote_reserves":0,
            "fee_config":{"account_authenticated":True,
                "flat_fees":standard,"exotic_flat_fees":other,
                "fee_tiers":[{"market_cap_threshold":0,"fees":standard}],
                "stable_fee_tiers":[{"market_cap_threshold":0,"fees":other}]}}

    def test_differing_stable_fee_detected(self):
        p=self.pool()
        result=compare_fee_modes(p)
        self.assertEqual(result["status"],"FEE_MODE_AMBIGUOUS")
        self.assertIn("stable",result["candidate_modes"])
        self.assertFalse(result["fee_mode_verified"])

    def test_noncanonical_exotic_conflict(self):
        p=self.pool()
        p["canonical"]=False
        result=compare_fee_modes(p)
        self.assertIn("exotic",result["candidate_modes"])
        self.assertFalse(result["rates_equal"])

    def test_identical_rates_still_not_verified(self):
        p=self.pool()
        p["fee_config"]["stable_fee_tiers"]=p["fee_config"]["fee_tiers"]
        result=compare_fee_modes(p)
        self.assertEqual(result["status"],"MODE_RATES_EQUAL_UNVERIFIED")
        self.assertFalse(result["effective_fee_verified"])
        self.assertFalse(result["actionable"])

    def test_unavailable_alternate_does_not_masquerade_as_equal(self):
        p=self.pool()
        p["fee_config"]["stable_fee_tiers"]=[]
        result=compare_fee_modes(p)
        self.assertIn("stable",result["unavailable_modes"])
        self.assertFalse(result["rates_equal"])

    def test_authentication_required(self):
        p=self.pool()
        p["fee_config"]["account_authenticated"]=False
        with self.assertRaisesRegex(ValueError,"authenticated"):
            compare_fee_modes(p)
