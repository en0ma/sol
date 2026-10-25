import unittest
from arb.raydium_amm_v4_open_orders_reserves import decode_open_orders
from arb.orca_whirlpool import b58
MARKET=b58(bytes([1])*32);OWNER=b58(bytes([2])*32)
def sample():
 b=bytearray(3228);b[:5]=b"serum";b[-7:]=b"padding"
 b[5:13]=(5).to_bytes(8,"little");b[13:45]=bytes([1])*32;b[45:77]=bytes([2])*32
 for off,n in ((77,10),(85,100),(93,20),(101,200)):
  b[off:off+8]=n.to_bytes(8,"little")
 return b
class Tests(unittest.TestCase):
 def test_open_orders_totals_not_free_balance(self):
  x=decode_open_orders(bytes(sample()),market=MARKET,owner=OWNER)
  self.assertEqual(x["base_token_total"],100)
  self.assertEqual(x["quote_token_total"],200)
 def test_wrong_market_or_owner_fails(self):
  for market,owner in ((OWNER,OWNER),(MARKET,MARKET)):
   with self.assertRaises(ValueError):
    decode_open_orders(bytes(sample()),market=market,owner=owner)
 def test_wrong_account_kind_or_corrupt_balance_fails(self):
  b=sample();b[5:13]=(1).to_bytes(8,"little")
  with self.assertRaises(ValueError):decode_open_orders(bytes(b),market=MARKET,owner=OWNER)
  b=sample();b[77:85]=(101).to_bytes(8,"little")
  with self.assertRaises(ValueError):decode_open_orders(bytes(b),market=MARKET,owner=OWNER)
 def test_missing_padding_fails(self):
  b=sample();b[:5]=b"hello"
  with self.assertRaises(ValueError):decode_open_orders(bytes(b),market=MARKET,owner=OWNER)
if __name__=="__main__":unittest.main()
