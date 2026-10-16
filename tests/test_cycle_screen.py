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
        self.assertEqual(result["actual_quote_blockers"],{})

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

    @patch("arb.orca_multitick_quote.quote_from_decoded_arrays")
    def test_orca_leg_uses_amount_aware_tick_quote_but_not_executable(self,quote):
        route={"start_mint":"SOL","legs":[
            {"venue":"orca","pool":"whirlpool","input":"SOL","output":"USDC"},
            {"venue":"raydium_cpmm","pool":"cpmm","input":"USDC","output":"SOL"}]}
        indexed={
          ("orca","whirlpool"):{"verified":True,"slot":100},
          ("raydium_cpmm","cpmm"):{
              **self.pool("cpmm",[1000000,2000000]),"slot":100}}
        cfg={("raydium_cpmm","cpmm"):{"fee_verified_onchain":True,
                "trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":500}}
        quote.return_value={"mint_out":"USDC","amount_in":1000,
                            "estimated_output_base_units":2000,"ticks_crossed":1}
        q=score_cycle(route,indexed,cfg,1000,max_slot_spread=0,
                      orca_evidence={("orca","whirlpool"):{"verified":True,
                           "state":{"token_mint_a":"SOL","token_mint_b":"USDC"},
                           "arrays":[{"status":"FIXED_VALID"}]}})
        quote.assert_called_once()
        self.assertEqual(q["status"],"INDICATIVE_ONLY")
        self.assertEqual(q["legs_quoted"],2)
        self.assertFalse(q["actionable"])
        self.assertEqual(q["legs"][0]["ticks_crossed"],1)

    def test_missing_orca_tick_coverage_remains_unquotable(self):
        route={"start_mint":"SOL","legs":[
            {"venue":"orca","pool":"whirlpool","input":"SOL","output":"USDC"},
            {"venue":"raydium_cpmm","pool":"cpmm","input":"USDC","output":"SOL"}]}
        r=score_cycle(route,{("orca","whirlpool"):{"verified":True}}, {},1000)
        self.assertEqual(r["status"],"UNQUOTABLE")
        self.assertEqual(r["missing_quote_venue"],"orca")

    @patch("arb.cycle_screen.refresh")
    def test_real_quote_blockers_count_attempted_sizes(self,refresh):
        refresh.return_value={"verified_pools":[
            {"verified":True,"venue":"orca","address":"a","mints":["SOL","USDC"],"slot":1},
            {"verified":True,"venue":"raydium_clmm","address":"b","mints":["SOL","USDC"],"slot":1}],
            "rejected":[]}
        with patch("arb.whirlpool_ticks.inspect",side_effect=ValueError("missing ticks")):
            report=scan("rpc",[],amounts=(100,200))
        self.assertEqual(report["indicative_routes"],0)
        self.assertEqual(report["unquotable_routes"],report["screened_size_routes"])
        self.assertGreater(report["actual_quote_blockers"]["orca"]["unquotable_size_routes"],0)
        self.assertFalse(report["actionable_opportunities"])

    def test_clmm_and_cpmm_route_amounts_still_not_actionable(self):
        route={"start_mint":"SOL","legs":[
            {"venue":"raydium_clmm","pool":"clmm","input":"SOL","output":"USDC"},
            {"venue":"raydium_cpmm","pool":"cpmm","input":"USDC","output":"SOL"}]}
        indexed={("raydium_clmm","clmm"):{"verified":True,"slot":10},
                 ("raydium_cpmm","cpmm"):{
                     **self.pool("cpmm",[1000000,2000000]),"slot":10}}
        cfg={("raydium_cpmm","cpmm"):{"fee_verified_onchain":True,
             "trade_fee_rate_ppm":2500,"creator_fee_rate_ppm":500}}
        def quote(pool,mint,amount):
            self.assertEqual((pool,mint,amount),("clmm","SOL",1000))
            return {"status":"INDICATIVE_WITHIN_TICK_ONLY",
                    "mint_out":"USDC","amount_in":amount,
                    "estimated_output_base_units":2000,
                    "actionable":False,"executable_quote":False}
        result=score_cycle(route,indexed,cfg,1000,max_slot_spread=0,clmm_quote=quote)
        self.assertEqual(result["status"],"INDICATIVE_ONLY")
        self.assertEqual(result["legs_quoted"],2)
        self.assertFalse(result["actionable"])
        self.assertFalse(result["confirmed_profitable"])

    def test_clmm_provenance_rejects_executable_claim(self):
        route={"start_mint":"SOL","legs":[
            {"venue":"raydium_clmm","pool":"clmm","input":"SOL","output":"USDC"},
            {"venue":"raydium_cpmm","pool":"cpmm","input":"USDC","output":"SOL"}]}
        indexed={("raydium_clmm","clmm"):{"verified":True,"slot":10},
                 ("raydium_cpmm","cpmm"):{"verified":True,"slot":10}}
        result=score_cycle(route,indexed,{},1000,
            clmm_quote=lambda *args:{"status":"INDICATIVE_WITHIN_TICK_ONLY",
                "mint_out":"USDC","amount_in":1000,
                "estimated_output_base_units":2000,"actionable":True,
                "executable_quote":True})
        self.assertEqual(result["status"],"UNQUOTABLE")
