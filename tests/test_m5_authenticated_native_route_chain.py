import unittest
from arb.m5_authenticated_native_route_chain import chain

class NativeChainTests(unittest.TestCase):
    def route(self,hops):
        m=["A","B","C","D","E","F"][:hops]+["A"]
        return {"hops":hops,"start_mint":"A","legs":[
            {"venue":"orca","pool":"pool"+str(i),"input":m[i],"output":m[i+1]}
            for i in range(hops)]}
    def quote(self,leg,amount):
        return {"venue":leg["venue"],"pool":leg["pool"],"input_mint":leg["input"],
                "output_mint":leg["output"],"amount_in":amount,"amount_out":amount+1,
                "snapshot_slot":14,"source_authenticated":True,"source_quote_verified":True,
                "protocol_exact_verified":True,"actionable":False,
                "live_execution_approved":False,"broadcast":False}
    def test_two_through_six_chain_exact_amounts(self):
        for hops in range(2,7):
            with self.subTest(hops=hops):
                seen=[]
                def q(leg,amount):
                    seen.append(amount)
                    return self.quote(leg,amount)
                report=chain(self.route(hops),initial_input=100,quote_leg=q)
                self.assertEqual(seen,list(range(100,100+hops)))
                self.assertEqual(report["gross_delta_start_mint_units"],hops)
                self.assertFalse(report["net_profit_verified"])
                self.assertFalse(report["signed_simulation_verified"])
                self.assertFalse(report["broadcast"])
    def test_rejects_quote_without_protocol_exact_proof(self):
        def q(leg,amount):
            result=self.quote(leg,amount)
            result["protocol_exact_verified"]=False
            return result
        with self.assertRaisesRegex(ValueError,"source/exact-quote"):
            chain(self.route(4),initial_input=100,quote_leg=q)
    def test_rejects_mixed_snapshot_slots(self):
        count=[0]
        def q(leg,amount):
            count[0]+=1
            result=self.quote(leg,amount)
            result["snapshot_slot"]=14+count[0]
            return result
        with self.assertRaisesRegex(ValueError,"unsynchronized"):
            chain(self.route(4),initial_input=100,quote_leg=q)
    def test_rejects_spoofed_pool_or_amount(self):
        for field,bad in (("pool","other"),("amount_in",99),("source_authenticated",False)):
            with self.subTest(field=field):
                def q(leg,amount):
                    result=self.quote(leg,amount)
                    result[field]=bad
                    return result
                with self.assertRaises(ValueError):
                    chain(self.route(2),initial_input=100,quote_leg=q)
    def test_rejects_broken_route_and_live_action(self):
        route=self.route(3)
        route["legs"][1]["input"]="OTHER"
        with self.assertRaisesRegex(ValueError,"discontinuity"):
            chain(route,initial_input=100,quote_leg=self.quote)
        def q(leg,amount):
            result=self.quote(leg,amount)
            result["broadcast"]=True
            return result
        with self.assertRaisesRegex(ValueError,"safety"):
            chain(self.route(3),initial_input=100,quote_leg=q)

if __name__=="__main__":unittest.main()
