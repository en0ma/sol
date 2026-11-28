import unittest
from unittest.mock import patch
from arb.atomic_graph_coordinator import signed_packet
class PacketDiagnosticsTests(unittest.TestCase):
    def test_oversized_legacy_packet_reports_actual_bytes_and_remedy(self):
        class DummyTransaction:
            def verify(self):pass
            def __bytes__(self):return bytes(1320)
        class DummySigner:
            def pubkey(self):return "owner"
        class DummyHash:
            @staticmethod
            def from_string(s):return "hash"
        class DummyTxFactory:
            @staticmethod
            def new_signed_with_payer(*args):return DummyTransaction()
        import sys,types
        with patch.dict(sys.modules,{
            "solders.transaction":types.SimpleNamespace(Transaction=DummyTxFactory),
            "solders.hash":types.SimpleNamespace(Hash=DummyHash)}),patch(
            "arb.rpc.call",return_value={"value":{"blockhash":"hash"}}):
            with self.assertRaisesRegex(ValueError,"1320 > 1232.*v0 address lookup"):
                signed_packet("http://127.0.0.1:8899",[object(),object()],DummySigner())
if __name__=="__main__":unittest.main()
