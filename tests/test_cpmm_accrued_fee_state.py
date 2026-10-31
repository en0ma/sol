import unittest
from unittest.mock import patch
from arb.raydium_cpmm import decode,SIZE,DISC
class Tests(unittest.TestCase):
 @patch("arb.raydium_cpmm.b58",side_effect=lambda data:data.hex())
 def test_fee_liabilities_at_deployed_pool_offsets(self,_):
  b=bytearray(SIZE);b[:8]=DISC
  for i in range(10):b[8+32*i:40+32*i]=bytes([i+1])*32
  for offset,value in ((341,17),(349,19),(357,23),(365,29),(397,31),(405,37)):
   b[offset:offset+8]=value.to_bytes(8,"little")
  s=decode(bytes(b))
  self.assertEqual([s[k] for k in ("protocol_fees_token_0","protocol_fees_token_1",
      "fund_fees_token_0","fund_fees_token_1","creator_fees_token_0","creator_fees_token_1")],
      [17,19,23,29,31,37])
if __name__=="__main__":unittest.main()
