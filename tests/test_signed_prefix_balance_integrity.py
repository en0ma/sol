import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import verify_signed_prefix_balances
class Tests(unittest.TestCase):
    def check(self,balances,index,amounts):
        used=0
        def decode(raw):
            nonlocal used
            i=used;used+=1
            return {"mint":["A","B","C","D"][i],"authority":"owner",
                    "amount_base_units":balances[i]}
        accounts=[{"owner":"token","data":["YQ==","base64"]} for _ in balances]
        accounts.extend([None]*(4-len(accounts)))
        with patch("arb.token_vaults.decode_token_account",side_effect=decode),patch(
            "arb.token_vaults.TOKEN_PROGRAM","token"):
            return verify_signed_prefix_balances(
                {"accounts":accounts},["A","B","C","D"],"owner",100,amounts,index)
    def test_valid_cumulative_prefix(self):
        self.assertEqual(self.check([0,0,41],1,[100,50]),41)
    def test_nonzero_previous_intermediate_rejected(self):
        with self.assertRaisesRegex(ValueError,"residual"):
            self.check([0,9,41],1,[100,50])
    def test_initial_debit_rejected(self):
        with self.assertRaisesRegex(ValueError,"debit"):
            self.check([3,0,41],1,[100,50])
    def test_missing_touched_account_rejected(self):
        with self.assertRaisesRegex(ValueError,"absent"):
            self.check([0,0],1,[100,50])
if __name__=="__main__":unittest.main()
