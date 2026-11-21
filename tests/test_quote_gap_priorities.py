import unittest
from unittest.mock import patch
from arb.cycle_screen import scan,score_cycle
class QuoteGapTests(unittest.TestCase):
    @patch("arb.cycle_screen.read_pool_config")
    @patch("arb.cycle_screen.refresh")
    def test_rank_missing_venue_by_blocked_legs(self,refresh,read):
        refresh.return_value={"rejected":[],"verified_pools":[
            {"venue":"orca","address":"a","verified":True,"mints":["SOL","USDC"]},
            {"venue":"raydium_cpmm","address":"b","verified":True,"mints":["SOL","USDC"],"vault_base_units":[1000000,1000000]},
            {"venue":"orca","address":"c","verified":True,"mints":["USDC","RAY"]},
            {"venue":"orca","address":"d","verified":True,"mints":["RAY","SOL"]}]}
        read.return_value={"fee_verified_onchain":True,"trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":500}
        out=scan("rpc",[],(1000,))
        self.assertGreater(out["cycles_discovered"],0)
        self.assertEqual(out["quote_gap_priorities"][0]["venue"],"orca")
        self.assertGreater(out["quote_gap_priorities"][0]["blocked_route_legs"],0)
        self.assertEqual(out["actionable_opportunities"],0)
    def test_unsupported_venue_identified(self):
        route={"start_mint":"SOL","legs":[{"venue":"orca","pool":"p","input":"SOL","output":"USDC"}]}
        index={("orca","p"):{"verified":True}}
        x=score_cycle(route,index,{},1000)
        self.assertEqual(x["missing_quote_venue"],"orca")
