import unittest
from arb.whirlpool_swap import encode_swap,DISC
class OrcaExactOutputTests(unittest.TestCase):
    def test_exact_output_payload(self):
        data=encode_swap(90000,5314,79226673515401279992447579055,False,False)
        self.assertEqual(data[:8],DISC)
        self.assertEqual(int.from_bytes(data[8:16],"little"),90000)
        self.assertEqual(int.from_bytes(data[16:24],"little"),5314)
        self.assertEqual(data[-2:],b"\\x00\\x00")
