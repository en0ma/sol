"""The 200-route scout must explore distinct pools for each start token."""
import unittest

from arb.m5_three_hop_atomic_inventory import choose_pool_diverse_candidate


def route(*pools):
    return {"legs": [
        {"venue": "orca", "pool": pool} for pool in pools]}


class StartPoolDiversityTests(unittest.TestCase):
    def test_per_start_new_pools_beat_globally_new_but_locally_reused(self):
        # A globally unselected pool is not useful if most of the route
        # keeps reusing the same unusable pool for this mint.
        q = [
            ("reused", route("broken", "shared", "globally-new")),
            ("alternate", route("broken", "alternate1", "alternate2")),
        ]
        all_used = {("orca", k) for k in
                    ("broken", "shared", "alternate1", "alternate2")}
        local_used = {("orca", k) for k in ("broken", "shared")}
        identity, selected = choose_pool_diverse_candidate(
            q, set(), all_used, start_used_pools=local_used)
        self.assertEqual(identity, "alternate")
        self.assertEqual(len(q), 1)
        self.assertEqual(selected["legs"][-1]["pool"], "alternate2")

    def test_bounded_search_retains_initial_pool_order_when_window_one(self):
        q = [
            ("first", route("a", "b", "c")),
            ("second", route("a", "d", "e")),
        ]
        choice = choose_pool_diverse_candidate(
            q, set(), set(), start_used_pools={("orca", "a")},
            window=1)
        self.assertEqual(choice[0], "first")

    def test_no_duplicate_signed_route_identity_selected(self):
        q = [("prior", route("a", "b", "c")),
             ("available", route("a", "b", "d"))]
        choice = choose_pool_diverse_candidate(
            q, {"prior"}, set(), start_used_pools=set())
        self.assertEqual(choice[0], "available")
        self.assertEqual(len(q), 1)


if __name__ == "__main__":
    unittest.main()
