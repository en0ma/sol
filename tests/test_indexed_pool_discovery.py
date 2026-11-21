import unittest
from arb.indexed_pool_discovery import extract_meteora_candidates

ADDR="HtoZbnFf7BDGvPg3RxwiXN5pPG7hLa78XVGscLF9fkYV"
class IndexerCandidateTests(unittest.TestCase):
    def test_candidate_is_never_verified(self):
        entries=extract_meteora_candidates("meteora_damm_v2",
                                           {"data":[{"address":ADDR},{"address":ADDR}]})
        self.assertEqual(len(entries),1)
        self.assertFalse(entries[0]["verified"])
        self.assertFalse(entries[0]["actionable"])
    def test_rejects_unknown_layout(self):
        with self.assertRaises(ValueError):
            extract_meteora_candidates("meteora_dlmm",{"unexpected":[]})
    def test_rejects_untrusted_identity(self):
        self.assertEqual(extract_meteora_candidates("meteora_dlmm",
                         [{"address":"not-an-address"}]),[])
