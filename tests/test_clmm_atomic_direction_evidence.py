import unittest
from arb.next_ten_signed_atomic_offline import clmm_direction_evidence

class CLMMSignedDirectionEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.pool={"token_mint_0":"A","token_mint_1":"B"}
        self.direction={"0_to_1":["a","b","c"],"1_to_0":["d","e","f"]}
        self.accounts={x:{} for x in "abcdef"}
    def test_source_authenticated_arrays_selected_by_mint(self):
        a=clmm_direction_evidence(self.pool,"A",self.direction,self.accounts)
        b=clmm_direction_evidence(self.pool,"B",self.direction,self.accounts)
        self.assertEqual(a["tick_arrays"],["a","b","c"])
        self.assertEqual(b["tick_arrays"],["d","e","f"])
        self.assertTrue(a["tick_arrays_authenticated"])
    def test_fails_closed_if_required_array_not_exported(self):
        with self.assertRaisesRegex(ValueError,"absent"):
            clmm_direction_evidence(self.pool,"A",self.direction,{"a":{},"b":{}})
    def test_fails_closed_on_unsupported_mint(self):
        with self.assertRaisesRegex(ValueError,"mismatches"):
            clmm_direction_evidence(self.pool,"C",self.direction,self.accounts)
    def test_rejects_incomplete_or_reused_arrays(self):
        with self.assertRaisesRegex(ValueError,"triplet"):
            clmm_direction_evidence(self.pool,"A",{"0_to_1":["a","a","b"]},self.accounts)

if __name__=="__main__":unittest.main()
