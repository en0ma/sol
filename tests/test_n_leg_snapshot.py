import unittest
from unittest.mock import patch
from arb.damm_cpmm_atomic_offline import _post
class Tests(unittest.TestCase):
    def test_four_distinct_accounts_for_three_hop(self):
        rows=[{"owner":"token","executable":False,"data":["YQ==","base64"]} for _ in range(4)]
        with patch("arb.damm_cpmm_atomic_offline.call",return_value={"context":{"slot":1},"value":rows}),patch(
            "arb.damm_cpmm_atomic_offline.decode_token_account",create=True) as unused,patch(
            "arb.token_vaults.decode_token_account",side_effect=[
                {"mint":x,"authority":"owner","amount_base_units":100 if i==0 else 0}
                for i,x in enumerate(["A","B","A","B"])]),patch(
            "arb.damm_cpmm_atomic_offline.TOKEN_PROGRAM","token"):
            self.assertEqual(_post("rpc",["a","b","c","d"],["A","B","A","B"],"owner"),[100,0,0,0])
    def test_duplicate_user_account_rejected(self):
        with self.assertRaisesRegex(ValueError,"invalid aligned"):
            _post("rpc",["a","b","a","d"],["A","B","A","B"],"owner")
if __name__=="__main__":unittest.main()
