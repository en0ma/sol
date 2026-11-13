import copy,unittest
from arb.source_snapshot_manifest import digest,verify
class TestManifest(unittest.TestCase):
 def fixture(self):
    x={"one":{"data":["AQ==","base64"],"owner":"owner","lamports":9},
       "two":{"data":["Ag==","base64"],"owner":"owner","lamports":10}}
    return {"accounts":x,"state_account_addresses":["one","two"],
       "state_accounts_observed_slot":123,"state_account_count":2,
       "state_account_manifest_sha256":digest(x,["one","two"],123)}
 def test_hash_is_order_independent(self):
    f=self.fixture()
    self.assertEqual(digest(f["accounts"],["two","one"],123),f["state_account_manifest_sha256"])
    self.assertTrue(verify(f))
 def test_changed_balance_or_account_fails(self):
    for field in ("lamports","data"):
      f=self.fixture()
      f["accounts"]["one"][field]=0 if field=="lamports" else ["AA==","base64"]
      with self.assertRaises(ValueError):verify(f)
 def test_slot_and_membership_bound(self):
    f=self.fixture();f["state_accounts_observed_slot"]=124
    with self.assertRaises(ValueError):verify(f)
    f=self.fixture();f["state_account_addresses"]=["one"]
    with self.assertRaises(ValueError):verify(f)
 def test_invalid_inventory_count_rejected(self):
    f=self.fixture();f["state_account_count"]=1
    with self.assertRaises(ValueError):verify(f)
 def test_missing_checksum_rejected(self):
    f=self.fixture();del f["state_account_manifest_sha256"]
    with self.assertRaises(ValueError):verify(f)
if __name__=="__main__":unittest.main()
