"""DBC registry admission must reject unaudited CI and duplicate identities."""
import unittest
from arb.meteora_dbc_signed_registry_merge import merge


class DbCRegistrySafetyTests(unittest.TestCase):
    def test_original_unsigned_source_never_admitted(self):
        registry={"pools":[]}
        with self.assertRaisesRegex(ValueError,"prerequisite"):
            merge(registry,{}, {}, {}, {},required=1)
        self.assertEqual(registry,{"pools":[]})

    def test_shared_registry_duplicate_identity_fails_before_insertion(self):
        registry={"pools":[{"venue":"orca","address":"duplicate"},
                           {"venue":"orca","address":"duplicate"}]}
        with self.assertRaises(ValueError):
            merge(registry,{}, {}, {}, {},required=1)

    def test_require_six_signed_pool_count_bound(self):
        with self.assertRaisesRegex(ValueError,"1-6"):
            merge({"pools":[]},{},{},{},{},required=7)


if __name__=="__main__":unittest.main()
