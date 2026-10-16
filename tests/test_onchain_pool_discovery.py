import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import search_pair,discover,VENUES,MINTS
class DiscoveryTests(unittest.TestCase):
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_filters_both_mint_orders(self,call):
        a,b=MINTS["WSOL"],MINTS["USDT"]
        self.assertEqual(search_pair("rpc","orca",a,b),{})
        self.assertEqual(call.call_count,2)
        first=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual(first[1]["memcmp"],{"offset":101,"bytes":a})
        self.assertEqual(first[2]["memcmp"],{"offset":181,"bytes":b})
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_ray_offsets(self,call):
        search_pair("rpc","raydium_cpmm",MINTS["WSOL"],MINTS["USDT"])
        filt=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual([x["memcmp"]["offset"] for x in filt[1:]], [168,200])
    @patch("arb.onchain_pool_discovery.search_pair",return_value={})
    def test_absence_no_fake_opportunities(self,search):
        r=discover("rpc",[(MINTS["WSOL"],MINTS["USDT"])])
        self.assertEqual(r["status"],"COMPLETE")
        self.assertEqual(r["profitable_opportunities_confirmed"],0)
        self.assertEqual(r["pools_verified"],0)
    @patch("arb.onchain_pool_discovery.search_pair",side_effect=RuntimeError("429"))
    def test_partial_discovery_visible(self,search):
        r=discover("rpc",[(MINTS["WSOL"],MINTS["USDT"])])
        self.assertEqual(r["status"],"UPSTREAM_RATE_LIMITED")
        self.assertEqual(len(r["errors"]),1)
        search.assert_called_once()
    @patch("arb.onchain_pool_discovery.time.sleep")
    @patch("arb.onchain_pool_discovery.call",return_value=[])
    def test_paced_requests_preserve_two_order_filters(self,call,sleep):
        self.assertEqual(search_pair("rpc","pumpswap",MINTS["WSOL"],MINTS["USDC"],
                                     pace_seconds=2),{})
        self.assertEqual(sleep.call_count,2)
        sleep.assert_any_call(2)
        self.assertEqual(call.call_count,2)
    def test_invalid_pacing_rejected(self):
        with self.assertRaisesRegex(ValueError,"pacing"):
            search_pair("rpc","pumpswap",MINTS["WSOL"],MINTS["USDC"],pace_seconds=6)
    @patch("arb.pool_registry.refresh")
    @patch("arb.onchain_pool_discovery.search_pair",side_effect=RuntimeError("429"))
    def test_rate_limit_registry_fallback_is_distinct(self,search,refresh):
        refresh.return_value={"status":"COMPLETE","verified_count":1,
                              "verified_pools":[{"venue":"orca","address":"known",
                                  "mints":[MINTS["WSOL"],MINTS["USDT"]],
                                  "slot":12}]}
        r=discover("rpc",[(MINTS["WSOL"],MINTS["USDT"])],
                   registry_entries=[{"venue":"orca","address":"known"}])
        self.assertEqual(r["status"],"UPSTREAM_RATE_LIMITED")
        self.assertEqual(r["pools_verified"],0)
        self.assertEqual(r["direct_registry_fallback"]["verified_count"],1)
        self.assertEqual(r["candidate_graph_verified_count"],1)
        self.assertEqual(r["candidate_graph_pool_identities"][0]["address"],"known")
        search.assert_called_once()
        refresh.assert_called_once()
