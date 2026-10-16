import unittest
from unittest.mock import patch
from arb.cycle_screen import score_cycle,scan
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

    def test_disconnect_and_fake_start_rejected_before_quotes(self):
        indexed={("raydium_cpmm",p["address"]):p for p in (self.pool("a",[1000000,2000000]),self.pool("b",[2000000,1000000]))}
        cfg={k:{"fee_verified_onchain":True,"trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":500} for k in indexed}
        good=[{"input":"SOL","output":"USDC","venue":"raydium_cpmm","pool":"a"},
              {"input":"USDC","output":"SOL","venue":"raydium_cpmm","pool":"b"}]
        for bad in (
            {"start_mint":"FAKE","legs":good},
            {"start_mint":"SOL","legs":[good[0],{**good[1],"input":"SOL"}]},
            {"start_mint":"SOL","legs":[good[0],{**good[1],"output":"USDC"}]},
            {"start_mint":"SOL","legs":[good[0],{**good[1],"pool":"a"}]},
            {"start_mint":"SOL","legs":[good[0]]},
        ):
            with self.subTest(bad=bad):
                result=score_cycle(bad,indexed,cfg,10000)
                self.assertEqual(result["status"],"UNQUOTABLE")
                self.assertFalse(result["actionable"])

    def test_bad_fee_config_fails_closed_without_crash(self):
        pools=[self.pool("a",[1000000,2000000]),self.pool("b",[2000000,1000000])]
        indexed={("raydium_cpmm",p["address"]):p for p in pools}
        legs=[{"input":"SOL","output":"USDC","venue":"raydium_cpmm","pool":"a"},
              {"input":"USDC","output":"SOL","venue":"raydium_cpmm","pool":"b"}]
        for bad in ({"fee_verified_onchain":True,"trade_fee_rate_ppm":2500},
                    {"fee_verified_onchain":True,"trade_fee_rate_ppm":"2500","creator_fee_rate_ppm":500},
                    {"fee_verified_onchain":True,"trade_fee_rate_ppm":999999,"creator_fee_rate_ppm":500}):
            cfg={k:bad for k in indexed}
            with self.subTest(bad=bad):
                result=score_cycle({"start_mint":"SOL","legs":legs},indexed,cfg,1000)
                self.assertEqual(result["status"],"UNQUOTABLE")
                self.assertFalse(result["actionable"])

    def test_cross_pool_slot_freshness_gate(self):
        p1=self.pool("a",[1000000,2000000])
        p2=self.pool("b",[2000000,1000000])
        p1["slot"]=100
        p2["slot"]=109
        indexed={("raydium_cpmm",p["address"]):p for p in (p1,p2)}
        cfg={k:{"fee_verified_onchain":True,"trade_fee_rate_ppm":2500,
                "creator_fee_rate_ppm":500} for k in indexed}
        route={"start_mint":"SOL","legs":[
            {"input":"SOL","output":"USDC","venue":"raydium_cpmm","pool":"a"},
            {"input":"USDC","output":"SOL","venue":"raydium_cpmm","pool":"b"}]}
        stale=score_cycle(route,indexed,cfg,10000,max_slot_spread=8)
        self.assertEqual(stale["status"],"UNQUOTABLE")
        self.assertEqual(stale["slot_spread"],9)
        self.assertEqual(stale["legs_quoted"],0)
        p2["slot"]=108
        acceptable=score_cycle(route,indexed,cfg,10000,max_slot_spread=8)
        self.assertEqual(acceptable["status"],"INDICATIVE_ONLY")
        del p2["slot"]
        missing=score_cycle(route,indexed,cfg,10000,max_slot_spread=8)
        self.assertEqual(missing["reason"],"missing verified pool slot")
        self.assertFalse(missing["actionable"])

    def test_invalid_slot_budget_rejected(self):
        with self.assertRaises(ValueError):
            score_cycle({}, {}, {}, 100, max_slot_spread=True)

    @patch("arb.cycle_screen.read_pool_config")
    @patch("arb.cycle_screen.cycles")
    @patch("arb.cycle_screen.refresh")
    def test_scan_keeps_route_identity_and_same_mint_rankings(self,refresh,cycles,fees):
        p1=self.pool("a",[1000000,2000000])
        p2=self.pool("b",[2000000,1000000])
        p1["slot"]=p2["slot"]=500
        refresh.return_value={"rejected":[],"verified_pools":[p1,p2]}
        legs=[{"input":"SOL","output":"USDC","venue":"raydium_cpmm","pool":"a"},
              {"input":"USDC","output":"SOL","venue":"raydium_cpmm","pool":"b"}]
        cycles.return_value=[{"start_mint":"SOL","hops":2,"venues":["raydium_cpmm"],"legs":legs}]
        fees.return_value={"fee_verified_onchain":True,"trade_fee_rate_ppm":2500,
                           "creator_fee_rate_ppm":500}
        result=scan("localhost",[],amounts=(10000,20000))
        self.assertEqual(result["screened_size_routes"],2)
        self.assertEqual(result["indicative_routes"],2)
        self.assertEqual(result["candidate_rankings"][0]["route_legs"],legs)
        self.assertFalse(result["candidate_rankings"][0]["actionable"])
        self.assertEqual(result["max_pool_slot_spread"],8)

    @patch("arb.cycle_screen.read_pool_config")
    @patch("arb.cycle_screen.refresh")
    def test_extra_discovered_hints_reverified_and_deduplicated(self,refresh,fees):
        refresh.return_value={"verified_pools":[],"rejected":[]}
        entries=[{"venue":"orca","address":"known"}]
        extra=[{"venue":"orca","address":"known"},
               {"venue":"raydium_cpmm","address":"candidate"}]
        result=scan("rpc",entries,extra_entries=extra)
        self.assertEqual(result["validated_pools"],0)
        self.assertEqual(refresh.call_args.args[1],[
            {"venue":"orca","address":"known"},
            {"venue":"raydium_cpmm","address":"candidate"}])
        self.assertEqual(result["actionable_opportunities"],0)
