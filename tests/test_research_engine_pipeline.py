import unittest
from arb.research_engine_pipeline import authenticated_registry,run_cycle_pipeline
NOW=1000
POOLS=[{"venue":"orca","address":"p-orca","mints":["A","B"],"verified":True,"source_authenticated":True,"account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL","slot":500,"observed_unix":990},
       {"venue":"raydium_cpmm","address":"p-cpmm","mints":["A","B"],"verified":True,"source_authenticated":True,"account_owner_verified":True,"snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL","slot":500,"observed_unix":990}]
COSTS={"network_fee":2,"priority_fee":2,"compute_cost":2,"slippage_buffer":5,"quote_uncertainty_buffer":5}
class PipelineTests(unittest.TestCase):
 def test_reject_stale_pool_and_missing_evidence(self):
    stale=dict(POOLS[0],observed_unix=800)
    self.assertEqual(len(authenticated_registry([stale],now=NOW)["pools"]),0)
    report=run_cycle_pipeline([stale],now=NOW,quote_provider=lambda *x:None,cost_provider=lambda *x:COSTS)
    self.assertEqual(report["graph_cycles"],0)
    self.assertFalse(report["actionable"])
 def test_connected_graph_quote_without_execution_is_not_proof(self):
    def quote(leg,amount):
        n=amount if amount is not None else 1000
        return dict(leg,amount_in=n,amount_out=n+100,source_authenticated=True,
                    quote_source="authenticated-snapshot",observed_unix=995,
                    liquidity_input_units=100000)
    report=run_cycle_pipeline(POOLS,now=NOW,quote_provider=quote,cost_provider=lambda *x:COSTS)
    self.assertGreater(report["graph_cycles"],0)
    self.assertGreater(report["research_positive"],0)
    self.assertEqual(report["signed_simulated_candidates"],0)
    self.assertFalse(report["broadcast"])
    self.assertGreater(report["metrics"]["quote_attempted"],0)
    self.assertGreater(len(report["ranked_research_candidates"]),0)
    self.assertEqual(report["metrics"]["signed_unavailable"],report["research_positive"])
 def test_requested_exact_input_cannot_be_substituted_by_quote_provider(self):
    def forged_quote(leg,amount):
        # A fabricated first-leg input can make a gross spread look stronger
        # than the requested size while otherwise satisfying quote continuity.
        n=amount if amount is not None else 1000
        return dict(leg,amount_in=n+1,amount_out=n+101,
                    source_authenticated=True,quote_source="snapshot",
                    observed_unix=995,liquidity_input_units=100000)
    result=run_cycle_pipeline(POOLS,now=NOW,quote_provider=forged_quote,
                              cost_provider=lambda *x:COSTS,initial_input=1000)
    self.assertEqual(result["research_positive"],0)
    self.assertEqual(result["metrics"]["signed_attempted"],0)
    self.assertTrue(all(x["status"]=="UNASSESSABLE" for x in result["results"]))
    self.assertTrue(all("first quote does not consume requested exact input"
                        in x["reason_codes"][0] for x in result["results"]))
 def test_exact_input_boolean_forgery_is_rejected(self):
    def forged_quote(leg,amount):
        return dict(leg,amount_in=True,amount_out=1100,
                    source_authenticated=True,quote_source="snapshot",
                    observed_unix=995,liquidity_input_units=100000)
    result=run_cycle_pipeline(POOLS,now=NOW,quote_provider=forged_quote,
                              cost_provider=lambda *x:COSTS,initial_input=1)
    self.assertEqual(result["research_positive"],0)
    self.assertEqual(result["metrics"]["signed_attempted"],0)
 def test_later_hop_bool_and_overflow_cannot_reach_economics_or_signing(self):
    for bad in (True, False, -1, 0, 2**64, "1100"):
        calls={"cost":0,"signed":0}
        def quote(leg,amount):
            if leg["venue"]=="raydium_cpmm":
                return dict(leg,amount_in=bad,amount_out=1100,
                            source_authenticated=True,quote_source="snapshot",
                            observed_unix=995,liquidity_input_units=100000)
            return dict(leg,amount_in=1000,amount_out=1100,
                        source_authenticated=True,quote_source="snapshot",
                        observed_unix=995,liquidity_input_units=100000)
        def costs(*args):
            calls["cost"]+=1
            return COSTS
        def signed(*args):
            calls["signed"]+=1
            return {}
        result=run_cycle_pipeline(POOLS,now=NOW,quote_provider=quote,
                                  cost_provider=costs,simulate_provider=signed,
                                  initial_input=1000)
        self.assertEqual(result["metrics"]["signed_attempted"],0)
        self.assertTrue(all(row["status"]=="UNASSESSABLE" for row in result["results"]))
        self.assertEqual(calls,{"cost":0,"signed":0})
 def test_invalid_output_amount_cannot_enter_later_hop(self):
    for bad in (True, 0, -2, 2**64, None):
        calls={"cost":0}
        def quote(leg,amount):
            return dict(leg,amount_in=1000,amount_out=bad,
                        source_authenticated=True,quote_source="snapshot",
                        observed_unix=995,liquidity_input_units=100000)
        def costs(*args):
            calls["cost"]+=1
            return COSTS
        result=run_cycle_pipeline(POOLS,now=NOW,quote_provider=quote,
                                  cost_provider=costs,initial_input=1000)
        self.assertTrue(all(row["status"]=="UNASSESSABLE" for row in result["results"]))
        self.assertEqual(calls["cost"],0)
 def test_provider_wrong_identity_fails_closed(self):
    report=run_cycle_pipeline(POOLS,now=NOW,
        quote_provider=lambda leg,amount:dict(leg,pool="fake"),
        cost_provider=lambda *x:COSTS)
    self.assertEqual(report["research_positive"],0)
    self.assertTrue(all(x["status"]=="UNASSESSABLE" for x in report["results"]))
 def test_simulator_cannot_self_attest_success_without_receipt(self):
    def quote(leg,amount):
        n=amount or 1000
        return dict(leg,amount_in=n,amount_out=n+100,source_authenticated=True,
                    quote_source="snapshot",observed_unix=995,liquidity_input_units=100000)
    report=run_cycle_pipeline(POOLS,now=NOW,quote_provider=quote,
                              cost_provider=lambda *x:COSTS,
                              simulate_provider=lambda *x:{"signed_atomic_simulation_verified":True})
    self.assertEqual(report["signed_simulated_candidates"],0)
    self.assertGreater(report["metrics"]["signed_attempted"],0)
    self.assertGreater(report["metrics"]["signed_rejected"],0)
 def test_requires_independent_owner_and_origin_attestation(self):
    untrusted=dict(POOLS[0],account_owner_verified=False)
    result=authenticated_registry([untrusted],now=NOW)
    self.assertEqual(result["pools"],[])
    self.assertTrue(result["rejected"])
 def test_six_hop_source_bound_quotes_and_costs_remain_research_only(self):
    mints=["A","B","C","D","E","F"]
    venues=["orca","raydium_cpmm","raydium_clmm","raydium_amm_v4",
            "meteora_dlmm","pumpswap"]
    pools=[{**POOLS[0],"venue":venues[i],"address":"pool-"+str(i),
            "mints":[mints[i],mints[(i+1)%6]]} for i in range(6)]
    def quote(leg,amount):
        self.assertIsNotNone(amount)
        return {**leg,"amount_in":amount,"amount_out":amount+100,
                "source_authenticated":True,"quote_source":"authenticated-snapshot",
                "observed_unix":995,"liquidity_input_units":100000000}
    result=run_cycle_pipeline(pools,now=NOW,quote_provider=quote,
        cost_provider=lambda *args:COSTS,initial_input=1000,max_hops=6)
    self.assertTrue(any(len(x["route"]["legs"])==6 for x in result["results"]))
    self.assertTrue(any(len(x["route"]["legs"])==6 and
        x["research"]["status"]=="RESEARCH_CANDIDATE_ONLY" for x in result["results"]
        if "research" in x))
    self.assertEqual(result["signed_simulated_candidates"],0)
    self.assertFalse(result["broadcast"])
    with self.assertRaises(ValueError):
        run_cycle_pipeline(pools,now=NOW,quote_provider=quote,
            cost_provider=lambda *args:COSTS,max_hops=7)

 def test_cross_slot_skew_excludes_old_pool(self):
    old=dict(POOLS[0],slot=400)
    result=authenticated_registry([old,POOLS[1]],now=NOW)
    self.assertEqual(len(result["pools"]),1)
    self.assertEqual(result["max_slot"],500)
if __name__=="__main__":unittest.main()
