import base64
import unittest
from unittest.mock import patch
from arb.damm_v2_signed_preflight import authenticate_pool
from arb.meteora_damm_v2 import PROGRAM

POOL="58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2"
A="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
B="So11111111111111111111111111111111111111112"
STATE={"token_a_mint":A,"token_b_mint":B,"token_a_vault":"vaultA",
       "token_b_vault":"vaultB","pool_status":0,"token_a_flag":0,
       "token_b_flag":0,"liquidity":1,"sqrt_price":1}
EVIDENCE={"venue":"meteora_damm_v2","address":POOL,"slot":100,
          "vault_base_units":[200,300],"mints":[A,B]}

def account(owner=PROGRAM,slot=101):
    return {"context":{"slot":slot},
            "value":{"owner":owner,"executable":False,
                     "data":[base64.b64encode(b"valid").decode(),"base64"]}}

def verified(slot=102):
    return {"venue":"meteora_damm_v2","address":POOL,"slot":slot,
            "vault_base_units":[250,350],"mints":[A,B]}

class DammV2SignedPreflightTests(unittest.TestCase):
    @patch("arb.damm_v2_signed_preflight.verify",return_value=verified())
    @patch("arb.damm_v2_signed_preflight.decode",return_value=STATE)
    @patch("arb.damm_v2_signed_preflight.call",return_value=account())
    def test_refreshes_owner_decoder_and_vaults(self,rpc,decode,verify):
        result=authenticate_pool("http://localhost:8899",POOL,STATE,EVIDENCE)
        self.assertTrue(result["pool_reauthenticated"])
        self.assertEqual(result["authenticated_slot"],102)
        self.assertEqual(result["fresh_vault_base_units"],[250,350])
        self.assertEqual(rpc.call_args.args[1],"getAccountInfo")
        self.assertEqual(rpc.call_args.args[2][1]["minContextSlot"],100)
        verify.assert_called_once_with("http://localhost:8899",POOL,STATE)
        self.assertFalse(result["broadcast"])

    @patch("arb.damm_v2_signed_preflight.call")
    def test_rejects_untrusted_evidence_before_rpc(self,rpc):
        with self.assertRaisesRegex(ValueError,"authenticated"):
            authenticate_pool("http://localhost:8899",POOL,STATE,
                              {**EVIDENCE,"address":B})
        rpc.assert_not_called()

    @patch("arb.damm_v2_signed_preflight.call",return_value=account(owner=B))
    def test_wrong_program_owner_rejected(self,rpc):
        with self.assertRaisesRegex(ValueError,"owner or slot"):
            authenticate_pool("http://localhost:8899",POOL,STATE,EVIDENCE)

    @patch("arb.damm_v2_signed_preflight.decode",return_value={**STATE,"liquidity":2})
    @patch("arb.damm_v2_signed_preflight.call",return_value=account())
    def test_changed_pool_state_rejected(self,rpc,decode):
        with self.assertRaisesRegex(ValueError,"differs"):
            authenticate_pool("http://localhost:8899",POOL,STATE,EVIDENCE)

    @patch("arb.damm_v2_signed_preflight.verify",return_value=verified(slot=100))
    @patch("arb.damm_v2_signed_preflight.decode",return_value=STATE)
    @patch("arb.damm_v2_signed_preflight.call",return_value=account())
    def test_stale_vault_snapshot_rejected(self,rpc,decode,verify):
        with self.assertRaisesRegex(ValueError,"stale"):
            authenticate_pool("http://localhost:8899",POOL,STATE,EVIDENCE)

    @patch("arb.damm_v2_signed_preflight.call")
    def test_remote_rpc_rejected_without_fetch(self,rpc):
        with self.assertRaisesRegex(ValueError,"localhost"):
            authenticate_pool("https://api.mainnet-beta.solana.com",
                              POOL,STATE,EVIDENCE)
        rpc.assert_not_called()

if __name__=="__main__":
    unittest.main()
