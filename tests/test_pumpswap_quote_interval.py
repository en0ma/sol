import unittest
from arb.pumpswap_quote_interval import quote_candidate_interval


def pool():
    standard={"lp_fee_bps":100,"protocol_fee_bps":50,"creator_fee_bps":20}
    stable={"lp_fee_bps":40,"protocol_fee_bps":20,"creator_fee_bps":10}
    return {"venue":"pumpswap","verified":True,"canonical_pool_verified":True,
            "canonical":True,"base_mint":"BASE","quote_mint":"QUOTE",
            "base_mint_supply":1000000,"base_reserve":1000000,
            "quote_vault_balance":2000000,"virtual_quote_reserves":-100000,
            "protocol_fees_accrued":10000,"creator_fees_accrued":5000,
            "global_config":{"buy_enabled":True,"sell_enabled":True},
            "fee_config":{"account_authenticated":True,"flat_fees":standard,
                "exotic_flat_fees":stable,
                "fee_tiers":[{"market_cap_threshold":0,"fees":standard}],
                "stable_fee_tiers":[{"market_cap_threshold":0,"fees":stable}]}}


class PumpSwapQuoteIntervalTests(unittest.TestCase):
    def test_both_directions_and_uncertainty_interval(self):
        p=pool()
        for mint in ("BASE","QUOTE"):
            v=quote_candidate_interval(p,mint,100000)
            self.assertEqual(v["status"],"INDICATIVE_OUTPUT_INTERVAL_ONLY")
            self.assertLess(v["min_output_base_units"],v["max_output_base_units"])
            self.assertFalse(v["executable_quote"])
            self.assertEqual(len(v["candidate_outputs"]),2)

    def test_unavailable_fee_mode_does_not_claim_complete_bounds(self):
        p=pool()
        p["fee_config"]["stable_fee_tiers"]=[]
        v=quote_candidate_interval(p,"BASE",100000)
        self.assertEqual(v["status"],"INCOMPLETE_FEE_MODES")
        self.assertNotIn("min_output_base_units",v)

    def test_unverified_snapshot_and_direction_rejected(self):
        p=pool()
        p["verified"]=False
        with self.assertRaises(ValueError):
            quote_candidate_interval(p,"BASE",100000)
        p=pool()
        p["global_config"]["sell_enabled"]=False
        with self.assertRaisesRegex(ValueError,"disabled"):
            quote_candidate_interval(p,"BASE",100000)
        p=pool()
        p["creator_fees_accrued"]=None
        with self.assertRaisesRegex(ValueError,"accounting"):
            quote_candidate_interval(p,"BASE",100000)
