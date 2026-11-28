import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import audit_n_leg_cpi
class FakePub:
    def __init__(self,s):self.s=s
    @classmethod
    def from_string(cls,s):return cls(s)
    def __eq__(self,o):return isinstance(o,FakePub) and self.s==o.s
    def __str__(self):return self.s
class FakeTx:
    message=type("Msg",(),{"account_keys":[FakePub("token"),FakePub("A"),FakePub("B"),FakePub("C"),FakePub("D")]})()
class Tests(unittest.TestCase):
    def test_three_leg_cpi_each_hop_exact(self):
        def transfer(row,keys,token):return tuple(row)
        rows={"innerInstructions":[
          {"index":0,"instructions":[("A","B",90)]},
          {"index":1,"instructions":[("pool","C",81)]},
          {"index":2,"instructions":[("pool","D",70)]}]}
        # In real CPI the second leg includes its input debit and output credit.
        rows["innerInstructions"][1]["instructions"].insert(0,("B","pool",90))
        rows["innerInstructions"][2]["instructions"].insert(0,("C","pool",81))
        with patch("solders.pubkey.Pubkey",FakePub),patch("arb.token_vaults.TOKEN_PROGRAM","token"),patch(
            "arb.damm_cpmm_atomic_offline._inner_token_transfer",side_effect=transfer):
            result=audit_n_leg_cpi(FakeTx(),rows,["A","B","C","D"],[100,90,81])
        self.assertTrue(result["signed_cpi_per_leg_verified"])
        self.assertEqual(len(result["hops"]),2)
    def test_unspent_output_fails_even_if_accounts_have_no_residual(self):
        rows={"innerInstructions":[{"index":0,"instructions":[("A","B",90)]},
            {"index":1,"instructions":[("B","pool",80),("B","C",81)]},
            {"index":2,"instructions":[("C","pool",81)]}]}
        with patch("solders.pubkey.Pubkey",FakePub),patch("arb.token_vaults.TOKEN_PROGRAM","token"),patch(
            "arb.damm_cpmm_atomic_offline._inner_token_transfer",side_effect=lambda row,keys,token:tuple(row)):
            with self.assertRaisesRegex(ValueError,"mismatch hop 1"):
                audit_n_leg_cpi(FakeTx(),rows,["A","B","C","D"],[100,90,81])
    def test_missing_middle_group_fails(self):
        with patch("solders.pubkey.Pubkey",FakePub),patch("arb.token_vaults.TOKEN_PROGRAM","token"):
            with self.assertRaises(ValueError):
                audit_n_leg_cpi(FakeTx(),{"innerInstructions":[{"index":0,"instructions":[]}]},
                                 ["A","B","C"],[100,90])
    def test_independent_audit_checks_all_boundary_transfers(self):
        rows={"innerInstructions":[
            {"index":0,"instructions":[("A","pool",100),("pool","B",90)]},
            {"index":1,"instructions":[("B","pool",90),("pool","C",81)]},
            {"index":2,"instructions":[("C","pool",81),("pool","D",70)]}]}
        with patch("solders.pubkey.Pubkey",FakePub),patch("arb.token_vaults.TOKEN_PROGRAM","token"),patch(
            "arb.damm_cpmm_atomic_offline._inner_token_transfer",side_effect=lambda row,keys,token:tuple(row)):
            result=audit_n_leg_cpi(FakeTx(),rows,["A","B","C","D"],[100,90,81],terminal_output=70)
            self.assertTrue(result["all_boundary_transfers_verified"])
            self.assertEqual([x["input_debited_base_units"] for x in result["leg_boundary_transfers"]],[100,90,81])
            self.assertEqual([x["output_credited_base_units"] for x in result["leg_boundary_transfers"]],[90,81,70])
            with self.assertRaisesRegex(ValueError,"boundary amount mismatch"):
                audit_n_leg_cpi(FakeTx(),rows,["A","B","C","D"],[100,90,81],terminal_output=69)
            rows["innerInstructions"][0]["instructions"].append(("pool","D",1))
            with self.assertRaisesRegex(ValueError,"unexpected boundary transfer"):
                audit_n_leg_cpi(FakeTx(),rows,["A","B","C","D"],[100,90,81],terminal_output=70)
if __name__=="__main__":unittest.main()
