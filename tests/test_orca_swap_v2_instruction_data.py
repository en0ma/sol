import unittest
from arb.orca_swap_v2_instruction_data import DISCRIMINATOR,encode_swap_v2_data

class SwapV2EncodingTests(unittest.TestCase):
    def test_reference_discriminator_and_borsh_fields(self):
        self.assertEqual(list(DISCRIMINATOR),[43,4,237,11,26,201,30,98])
        data=encode_swap_v2_data(123,120,2**64,True,False)
        self.assertEqual(len(data),43)
        self.assertEqual(data[:8],DISCRIMINATOR)
        self.assertEqual(int.from_bytes(data[8:16],"little"),123)
        self.assertEqual(int.from_bytes(data[16:24],"little"),120)
        self.assertEqual(int.from_bytes(data[24:40],"little"),2**64)
        self.assertEqual(data[40:],bytes((1,0,0)))

    def test_unsupported_or_invalid_args_fail_closed(self):
        cases=[(0,0,2**64,True,True,None),
               (True,0,2**64,True,True,None),
               (1,-1,2**64,True,True,None),
               (1,0,0,True,True,None),
               (1,0,2**128,True,True,None),
               (1,0,2**64,1,True,None),
               (1,0,2**64,True,True,{})]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    encode_swap_v2_data(*args)

if __name__=="__main__":
    unittest.main()
