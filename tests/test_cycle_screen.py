import unittest
from arb.cycle_screen import score_cycle
class CycleScreenTests(unittest.TestCase):
    def pool(self,name,reserves):
        return {"venue":"raydium_cpmm","address":name,"verified":True,
                "mints":["SOL","USDC"],"vault_base_units":reserves}
    def test_cross_pool_roundtrip_quoted_but_not_actionable(self):
        p1=self.pool("a",[1000000,2000000]);p2=self.pool("b",[2000000,1000000])
        route={"start_mint":"SOL","legs":[
            {"input":"SOL","output":"USDC","venue":"raydium_cpmm","pool":"a"},
            {"input":"USDC","output":"SOL","venue":"raydium_cpmm","pool":"b"}]}
        indexed={("raydium_cpmm",p["address"]):p for p in (p1,p2)}
        cfg={k:{"fee_verified_onchain":True,"trade_fee_rate_ppm":2500,
                "creator_fee_rate_ppm":500} for k in indexed}
        q=score_cycle(route,indexed,cfg,10000)
        self.assertEqual(q["status"],"INDICATIVE_ONLY")
        self.assertEqual(q["legs_quoted"],2)
        self.assertFalse(q["actionable"])
        self.assertIsNone(q["estimated_net_base_units"])
    def test_unsupported_leg_must_not_be_ranked(self):
        route={"start_mint":"SOL","legs":[{"input":"SOL","output":"USDC",
            "venue":"orca","pool":"x"}]}
        self.assertEqual(score_cycle(route,{}, {},1000)["status"],"UNQUOTABLE")
    def test_fee_missing_rejected(self):
        route={"start_mint":"SOL","legs":[{"input":"SOL","output":"USDC",
            "venue":"raydium_cpmm","pool":"x"}]}
        self.assertEqual(score_cycle(route,{}, {},1000)["status"],"UNQUOTABLE")
