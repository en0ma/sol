import unittest
from unittest.mock import patch
from arb.atomic_v0_lookup import provision_offline_table
class V0LookupSafetyTests(unittest.TestCase):
    def test_v0_cannot_provision_without_offline_gate(self):
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with self.assertRaisesRegex(ValueError,"explicitly offline"):
                provision_offline_table("http://127.0.0.1:8899",[object()])
    def test_v0_refuses_remote_rpc(self):
        with self.assertRaises(ValueError):
            provision_offline_table("https://api.mainnet-beta.solana.com",[object()])
    def test_empty_lookup_rejected(self):
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            with self.assertRaisesRegex(ValueError,"invalid offline lookup"):
                provision_offline_table("http://127.0.0.1:8899",[])
if __name__=="__main__":unittest.main()
