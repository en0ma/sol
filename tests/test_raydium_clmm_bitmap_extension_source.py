"""Real PDA / fail-closed full-source bitmap extension reauthentication."""
import base64
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.raydium_clmm import PROGRAM
from arb.raydium_clmm_bitmap_extension_source import (
    bitmap_pda, attach_authenticated_bitmap, LENGTH, DISC)

POOL="61R1ndXxvsWXXkWSyNkCxnzwd3zUNB8Q2ibmkiLPC8ht"
def base():
    acct={"address":POOL,"owner":PROGRAM,"lamports":100,"account_base64":base64.b64encode(b"a").decode()}
    tick={"address":str(Pubkey.new_unique()),"owner":PROGRAM,"lamports":100,
          "account_base64":base64.b64encode(b"b").decode(),"present":True}
    source={"tick_array_source_slot":100,"synchronized_non_tick_accounts":[dict(acct) for _ in range(7)],
            "tick_arrays":[tick]}
    observed=[{"owner":a["owner"],"lamports":a["lamports"],"data":[a["account_base64"],"base64"]}
              for a in source["synchronized_non_tick_accounts"]+source["tick_arrays"]]
    raw=DISC+bytes(Pubkey.from_string(POOL))+bytes(LENGTH-40)
    ext={"owner":PROGRAM,"lamports":5000,"executable":False,"data":[base64.b64encode(raw).decode(),"base64"]}
    return source,observed,ext

class BitmapSourceTests(unittest.TestCase):
    def test_bitmap_pda_matches_original_program_seed(self):
        self.assertEqual(bitmap_pda(POOL),str(Pubkey.find_program_address(
            [b"pool_tick_array_bitmap_extension",bytes(Pubkey.from_string(POOL))],
            Pubkey.from_string(PROGRAM))[0]))
    def test_original_bitmap_is_hydratable_and_slot_bound(self):
        source,observed,ext=base()
        with patch("arb.raydium_clmm_bitmap_extension_source.call",return_value={
                "context":{"slot":101},"value":[*observed,ext]}) as rpc:
            out=attach_authenticated_bitmap("http://127.0.0.1:8899",POOL,source)
        self.assertTrue(out["bitmap_extension"]["present"])
        self.assertEqual(out["tick_array_source_slot"],101)
        self.assertEqual(rpc.call_args.args[2][1]["minContextSlot"],100)
    def test_absent_extension_is_explicit_not_fabricated(self):
        source,observed,_=base()
        with patch("arb.raydium_clmm_bitmap_extension_source.call",return_value={
                "context":{"slot":102},"value":[*observed,None]}):
            out=attach_authenticated_bitmap("http://127.0.0.1:8899",POOL,source)
        self.assertFalse(out["bitmap_extension"]["present"])
    def test_mutated_account_bytes_rejected(self):
        source,observed,ext=base()
        observed[0]["data"][0]=base64.b64encode(b"changed").decode()
        with patch("arb.raydium_clmm_bitmap_extension_source.call",return_value={
                "context":{"slot":101},"value":[*observed,ext]}):
            with self.assertRaisesRegex(ValueError,"source bytes changed"):
                attach_authenticated_bitmap("http://127.0.0.1:8899",POOL,source)
    def test_wrong_bitmap_parent_rejected(self):
        source,observed,ext=base()
        raw=DISC+bytes(Pubkey.new_unique())+bytes(LENGTH-40)
        ext["data"][0]=base64.b64encode(raw).decode()
        with patch("arb.raydium_clmm_bitmap_extension_source.call",return_value={
                "context":{"slot":101},"value":[*observed,ext]}):
            with self.assertRaisesRegex(ValueError,"original bytes invalid"):
                attach_authenticated_bitmap("http://127.0.0.1:8899",POOL,source)

if __name__=="__main__":
    unittest.main()
