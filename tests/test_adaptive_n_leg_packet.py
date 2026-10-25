import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import sign_adaptive_n_leg_offline
class FakePub:
    def __init__(self,s):self.s=s
    @classmethod
    def from_string(cls,s):return cls(s)
    def __str__(self):return self.s
    def __eq__(self,other):return str(self)==str(other)
class FakeSigner:
    def pubkey(self):return FakePub("payer")
class FakeIx:
    def __init__(self,p,accounts):self.program_id_index=p;self.accounts=accounts
class FakeMsg:
    account_keys=[FakePub(x) for x in ("payer","prog1","prog2","prog3","in1","in2")]
    instructions=[FakeIx(1,[4]),FakeIx(2,[4,5]),FakeIx(3,[5])]
class FakeTx:
    message=FakeMsg()
    def verify(self):pass
    def __bytes__(self):return b"a"*100
class FakeFactory:
    @staticmethod
    def new_signed_with_payer(*a):return FakeTx()
class Tests(unittest.TestCase):
    def test_three_linked_venue_instructions(self):
        from unittest.mock import MagicMock
        with patch("solders.hash.Hash.from_string",return_value=MagicMock()),patch(
                "arb.rpc.call",return_value={"value":{"blockhash":"x"}}),patch(
                "solders.transaction.Transaction",FakeFactory),patch(
                "solders.pubkey.Pubkey",FakePub):
            tx,lookup,proof=sign_adaptive_n_leg_offline("http://127.0.0.1:8899",
                 ["ix"]*3,FakeSigner(),programs=["prog1","prog2","prog3"],
                 intermediates=["in1","in2"])
        self.assertIsNone(lookup)
        self.assertTrue(proof["intermediate_account_linkage_verified"])
        self.assertFalse(proof["broadcast"])
    def test_reject_length_mismatch_before_rpc(self):
        with self.assertRaises(ValueError):
            sign_adaptive_n_leg_offline("http://127.0.0.1:8899",["ix"]*3,FakeSigner(),
                                        programs=["a","b"],intermediates=["m1","m2"])
if __name__=="__main__":unittest.main()
