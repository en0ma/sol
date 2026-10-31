import unittest
from unittest.mock import patch
from arb.cpmm_ammv4_signed_experiment import run
from arb.source_snapshot_manifest import digest
def fixture():
 a={"x":{"owner":"x","data":["AA==","base64"]}}
 return {"accounts":a,"state_account_addresses":["x"],"state_account_count":1,"state_accounts_observed_slot":7,
 "state_account_manifest_sha256":digest(a,["x"],7),"first_venue":"raydium_cpmm",
 "second_venue":"raydium_amm_v4","first_pool":"p","second_pool":"q","route_mints":["A","B","A"]}
def quote(venue,pool,src,dst,n):
 return {"venue":venue,"pool":pool,"input_mint":src,"output_mint":dst,"amount_in":n,
 "amount_out":80 if venue=="raydium_cpmm" else 110,"snapshot_slot":7}
class Tests(unittest.TestCase):
 def test_exact_second_leg_amount_and_diagnostic_status(self):
  calls=[]
  def cpmm(fixture,*,observed_unix,leg,amount_in):
   calls.append(amount_in);return {"quote":quote("raydium_cpmm","p","A","B",amount_in)}
  def v4(fixture,*,pool,input_mint,amount_in,observed_unix):
   calls.append(amount_in);return {"quote":quote("raydium_amm_v4","q","B","A",amount_in)}
  with patch("arb.cpmm_ammv4_signed_experiment.quote_cpmm_only",side_effect=cpmm),patch("arb.cpmm_ammv4_signed_experiment.quote_from_fixture",side_effect=v4),patch("arb.cpmm_ammv4_signed_experiment.compare",return_value={"signed_atomic_evidence_status":"UNVERIFIED"}):
   r=run(fixture(),{},amount_in=100,observed_unix=1)
  self.assertEqual(calls,[100,80])
  self.assertFalse(r["protocol_exact_accuracy_verified"])
  self.assertIsNone(r["observed_risk"])
 def test_wrong_pool_direction_fails(self):
  f=fixture();f["second_venue"]="orca"
  with self.assertRaises(ValueError):run(f,{},amount_in=100,observed_unix=1)
if __name__=="__main__":unittest.main()
