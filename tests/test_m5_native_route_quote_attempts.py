import unittest
from arb.m5_native_route_quote_attempts import attempt

class SourceNativeAttemptTests(unittest.TestCase):
    def graph(self):
        return {"status":"SOURCE_AUTHENTICATED_ROUTE_DISCOVERY_ONLY",
            "actionable":False,"live_execution_approved":False,"broadcast":False,
            "routes":[{"hops":2,"start_mint":"A","legs":[
                {"venue":"orca","pool":"one","input":"A","output":"B"},
                {"venue":"raydium_cpmm","pool":"two","input":"B","output":"A"}]}]}
    def test_missing_native_proof_blocks_all_amounts(self):
        r=attempt(self.graph(),quote_leg=lambda leg,amount:{
            "venue":leg["venue"],"pool":leg["pool"],
            "input_mint":leg["input"],"output_mint":leg["output"],
            "amount_in":amount,"amount_out":amount+10,
            "snapshot_slot":4,"source_authenticated":True,
            "source_quote_verified":False,"protocol_exact_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False})
        self.assertEqual(r["attempt_count"],3)
        self.assertEqual(r["full_native_quote_count"],0)
        self.assertEqual(r["net_profitable_verified_count"],0)
        self.assertTrue(all(a["status"]=="NATIVE_QUOTE_BLOCKED" for a in r["attempts"]))
    def test_authenticated_exact_chain_does_not_promote_profit(self):
        def q(leg,amount):
            return {"venue":leg["venue"],"pool":leg["pool"],
                "input_mint":leg["input"],"output_mint":leg["output"],
                "amount_in":amount,"amount_out":amount+10,
                "snapshot_slot":4,"source_authenticated":True,
                "source_quote_verified":True,"protocol_exact_verified":True,
                "actionable":False,"live_execution_approved":False,"broadcast":False}
        r=attempt(self.graph(),amounts=(100,),quote_leg=q)
        self.assertEqual(r["full_native_quote_count"],1)
        self.assertEqual(r["attempts"][0]["final_output"],120)
        self.assertFalse(r["attempts"][0]["signed_simulation_verified"])
        self.assertEqual(r["net_profitable_verified_count"],0)
    def test_invalid_source_status_rejected(self):
        report=self.graph()
        report["actionable"]=True
        with self.assertRaises(ValueError):
            attempt(report,quote_leg=lambda *_:None)

if __name__=="__main__":unittest.main()
