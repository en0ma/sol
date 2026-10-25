import unittest
from arb.adaptive_route_amount_planner import plan
class Tests(unittest.TestCase):
    def test_each_next_input_observed_for_six_legs(self):
        legs=[{"venue":str(i),"pool":str(i),"input_mint":str(i%3),"output_mint":str((i+1)%3)} for i in range(6)]
        p=plan(legs,100,lambda i,leg,n:{"signed_offline_observed":True,"output_base_units":n+i+1})
        self.assertEqual(p["amounts"],[100,101,103,106,110,115])
        self.assertFalse(p["atomic_execution_verified"])
    def test_final_leg_requires_no_fake_observation(self):
        legs=[{"venue":"a","pool":"a","input_mint":"x","output_mint":"y"},
              {"venue":"b","pool":"b","input_mint":"y","output_mint":"x"}]
        calls=[]
        def observe(i,leg,amount):
            calls.append(i)
            return {"signed_offline_observed":True,"output_base_units":22}
        p=plan(legs,11,observe)
        self.assertEqual(p["amounts"],[11,22])
        self.assertEqual(calls,[0])
        self.assertEqual(len(p["observations"]),1)
    def test_two_legs(self):
        legs=[{"venue":"v1","pool":"a","input_mint":"x","output_mint":"y"},
              {"venue":"v2","pool":"b","input_mint":"y","output_mint":"x"}]
        p=plan(legs,12,lambda i,l,n:{"signed_offline_observed":True,"output_base_units":n+2})
        self.assertEqual(p["amounts"],[12,14])
    def test_fake_unsigned_observation_rejected(self):
        legs=[{"venue":"v1","pool":"a","input_mint":"x","output_mint":"y"},
              {"venue":"v2","pool":"b","input_mint":"y","output_mint":"x"}]
        with self.assertRaises(ValueError):
            plan(legs,1,lambda i,l,n:{"output_base_units":2})
    def test_more_than_six_rejected(self):
        with self.assertRaises(ValueError):plan([{}]*7,1,lambda i,l,n:{})
if __name__=="__main__":unittest.main()
