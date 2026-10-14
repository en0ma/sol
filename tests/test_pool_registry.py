import unittest
from unittest.mock import patch
from arb.pool_registry import refresh
from arb.orca_whirlpool import SOL,USDC
class RegistryTests(unittest.TestCase):
    def test_unbounded_rejected(self):
        with self.assertRaises(ValueError):refresh("rpc",[{}]*201)
    @patch("arb.pool_registry.verify")
    @patch("arb.pool_registry.call")
    @patch("arb.pool_registry.VENUES",{"test":("prog",3,0,0,lambda data:{"ok":True})})
    def test_revalidated_shared_pair(self,call,verify):
        import base64
        call.return_value={"value":{"owner":"prog","executable":False,
          "data":[base64.b64encode(b"abc").decode(),"base64"]}}
        def checked(rpc,venue,address,state):
            return {"venue":venue,"address":address,"mints":[SOL,USDC],
                    "slot":22,"vault_base_units":[100,200]}
        verify.side_effect=checked
        entries=[{"venue":"test","address":"a"*32}]
        result=refresh("rpc",entries)
        self.assertEqual(result["verified_count"],1)
        self.assertEqual(result["rejected_count"],0)
    @patch("arb.pool_registry.call")
    def test_missing_pool_stays_rejected(self,call):
        call.return_value={"value":None}
        result=refresh("rpc",[{"venue":"orca","address":"1"*32}])
        self.assertEqual(result["verified_count"],0)
        self.assertEqual(result["status"],"PARTIAL")
        self.assertEqual(result["shared_pairs"],[])
