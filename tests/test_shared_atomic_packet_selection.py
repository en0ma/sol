import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import sign_atomic_offline

class SharedPacketSelectionTests(unittest.TestCase):
    @patch("arb.atomic_v0_lookup.sign_v0_offline")
    @patch("arb.atomic_v0_lookup.verify_v0_order")
    @patch("arb.signed_atomic_instruction_preflight.inspect_signed_legacy_order")
    @patch("arb.rpc.call")
    def test_legacy_first_no_venue_specific_fallback(self,call,inspect,verify_v0,sign_v0):
        from solders.keypair import Keypair
        from solders.hash import Hash
        from solders.instruction import Instruction,AccountMeta
        from solders.pubkey import Pubkey
        signer=Keypair()
        first=Pubkey.new_unique()
        second=Pubkey.new_unique()
        mid=Pubkey.new_unique()
        ix1=Instruction(first,b"1",[AccountMeta(mid,False,True)])
        ix2=Instruction(second,b"2",[AccountMeta(mid,False,True)])
        call.return_value={"value":{"blockhash":str(Hash.default())}}
        inspect.return_value={"instruction_order_verified":True}
        tx,lookup,_=sign_atomic_offline(
            "http://127.0.0.1:8899",[ix1,ix2],signer,
            programs=[str(first),str(second)],intermediate=str(mid))
        self.assertIsNone(lookup)
        sign_v0.assert_not_called()
        verify_v0.assert_not_called()
    def test_rejects_same_program_twice(self):
        with self.assertRaisesRegex(ValueError,"distinct"):
            sign_atomic_offline("http://127.0.0.1:8899",[object(),object()],object(),
                                programs=["one","one"],intermediate="mid")
if __name__=="__main__":unittest.main()
