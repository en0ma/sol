import unittest
from unittest.mock import patch
from arb.onchain_pool_discovery import search_pair,verify_amm_v4,AMM_V4_PROGRAM,MINTS
from arb.token_vaults import TOKEN_PROGRAM

class AmmV4DiscoveryTests(unittest.TestCase):
    def test_canonical_base_quote_offsets(self):
        with patch("arb.onchain_pool_discovery.call",return_value=[]) as call:
            search_pair("rpc","raydium_amm_v4",MINTS["WSOL"],MINTS["USDC"])
        filters=call.call_args_list[0].args[2][1]["filters"]
        self.assertEqual(filters[0],{"dataSize":752})
        self.assertEqual([f["memcmp"]["offset"] for f in filters[1:]],[400,432])
        self.assertEqual(call.call_count,2)

    def test_pool_and_orderbook_owner_are_revalidated(self):
        state={"status":6,"base_vault":"A"*44,"quote_vault":"B"*44,
               "base_mint":MINTS["WSOL"],"quote_mint":MINTS["USDC"],
               "open_orders":"C"*44,"market_id":"D"*44,
               "market_program":"E"*44}
        pool={"owner":AMM_V4_PROGRAM,"executable":False,"data":["AAAA","base64"]}
        vault={"owner":TOKEN_PROGRAM,"executable":False,"data":["AAAA","base64"]}
        order={"owner":state["market_program"],"executable":False}
        response={"context":{"slot":99},"value":[pool,vault,vault,order,order]}
        def inspect(data):
            with patch("arb.onchain_pool_discovery.call",return_value=data),\
                 patch("arb.onchain_pool_discovery.decode_amm_v4",return_value=state),\
                 patch("arb.onchain_pool_discovery.decode_token_account",
                       side_effect=[{"mint":MINTS["WSOL"],"amount_base_units":12},
                                    {"mint":MINTS["USDC"],"amount_base_units":13}]):
                return verify_amm_v4("rpc","P"*44,state)
        verified=inspect(response)
        self.assertEqual(verified["vault_base_units"],[12,13])
        self.assertFalse(verified["protocol_exact_quote_verified"])
        forged=dict(response)
        forged["value"]=[pool,vault,vault,{"owner":"forged","executable":False},order]
        with self.assertRaisesRegex(ValueError,"OpenOrders"):
            inspect(forged)

if __name__=="__main__":
    unittest.main()
