import base64,unittest
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.raydium_cpmm import PROGRAM as CPMM
from arb.raydium_clmm import PROGRAM as CLMM
from arb.cpmm_config import DISC as C_DISC,CONFIG_SIZE
from arb.raydium_clmm_fee_snapshot import DISC as L_DISC
def fixture(addr,owner,data):
 return {"state_account_addresses":[addr],"accounts":{
 addr:{"owner":owner,"executable":False,"data":[base64.b64encode(data).decode(),"base64"]}}}
class Tests(unittest.TestCase):
 def test_cpmm_zero_creator_fee_exposes_trade_fee(self):
  b=bytearray(CONFIG_SIZE);b[:8]=C_DISC;b[12:20]=(2500).to_bytes(8,"little")
  f=fixture("config",CPMM,bytes(b))
  r=decode_native_config_fee("raydium_cpmm",{"amm_config":"config"},f)
  self.assertEqual(r["effective_quote_fee_ppm"],2500)
  self.assertTrue(r["total_effective_fee_authenticated"])
  self.assertFalse(r["broadcast"])
 def test_cpmm_creator_fee_blocks_effective_fee_claim(self):
  b=bytearray(CONFIG_SIZE);b[:8]=C_DISC;b[12:20]=(2500).to_bytes(8,"little")
  b[108:116]=(100).to_bytes(8,"little")
  r=decode_native_config_fee("raydium_cpmm",{"amm_config":"config"},fixture("config",CPMM,bytes(b)))
  self.assertIsNone(r["effective_quote_fee_ppm"])
  self.assertFalse(r["total_effective_fee_authenticated"])
 def test_clmm_layout_and_tick_spacing(self):
  b=bytearray(53);b[:8]=L_DISC;b[47:51]=(3000).to_bytes(4,"little")
  b[51:53]=(64).to_bytes(2,"little")
  state={"amm_config":"config","tick_spacing":64}
  r=decode_native_config_fee("raydium_clmm",state,fixture("config",CLMM,bytes(b)))
  self.assertEqual(r["effective_quote_fee_ppm"],3000)
  with self.assertRaises(ValueError):
   decode_native_config_fee("raydium_clmm",dict(state,tick_spacing=32),fixture("config",CLMM,bytes(b)))
 def test_untrusted_owner_and_inventory_fail(self):
  b=bytearray(CONFIG_SIZE);b[:8]=C_DISC
  with self.assertRaises(ValueError):
   decode_native_config_fee("raydium_cpmm",{"amm_config":"config"},fixture("config","wrong",bytes(b)))
  f=fixture("config",CPMM,bytes(b));f["state_account_addresses"]=[]
  with self.assertRaises(ValueError):
   decode_native_config_fee("raydium_cpmm",{"amm_config":"config"},f)
 def test_other_venues_do_not_inherit_guessed_fee(self):
  for v in ("orca","meteora_dlmm","meteora_damm_v2","pumpswap","raydium_amm_v4"):
   with self.assertRaises(ValueError):decode_native_config_fee(v,{}, {})
if __name__=="__main__":unittest.main()
