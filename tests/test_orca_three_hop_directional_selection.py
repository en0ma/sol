import unittest
from arb.orca_three_hop_fixture_export import select_directional_routes
from arb.orca_whirlpool import SOL

A="3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"
B="cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij"
P=["B5EwJVDuAauzUEEdwvbuXzbFFgEYnUqqS37TUM1c4PQA",
   "4v8ufj8Hj7UvFgtofQJAtzUud5xomwZfEqfCTHZ4wM72",
   "CeaZcxBNLpJWtxzt58qQmfMBtJY8pQLvursXTJYGQpbN"]
def route(tokens,pools):
    return {"tokens":tokens,"all_directional_tick_arrays_ready":True,
            "legs":[{"venue":"orca","pool":pools[i],
                     "from":tokens[i],"to":tokens[i+1]} for i in range(3)]}

class DirectionalSelectionTests(unittest.TestCase):
    def test_reversed_triangle_is_distinct_direction_but_same_pool_set(self):
        forward=route([SOL,A,B,SOL],P)
        reverse=route([SOL,B,A,SOL],list(reversed(P)))
        selected,pool_sets=select_directional_routes(
            {"routes":[forward,forward,reverse]})
        self.assertEqual(selected,[0,2])
        self.assertEqual(pool_sets,1)

    def test_unready_and_nonclosing_rejected(self):
        bad=route([SOL,A,B,A],P)
        unready=route([SOL,A,B,SOL],P)
        unready["all_directional_tick_arrays_ready"]=False
        self.assertEqual(select_directional_routes({"routes":[bad,unready]}),([],0))

    def test_cap_is_bounded(self):
        with self.assertRaises(ValueError):
            select_directional_routes({"routes":[]},max_routes=100)
