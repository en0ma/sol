import base64
import unittest
from unittest.mock import patch
from arb.chain_token_pair_labels import parse_metadata,fetch_labels,annotate_report,PROGRAM
from arb.orca_whirlpool import SOL,USDC

class TokenLabelTests(unittest.TestCase):
    def test_mint_bound_symbol_decoding_and_forged_mint_rejection(self):
        from solders.pubkey import Pubkey
        raw=(b"\x04"+b"\x11"*32+bytes(Pubkey.from_string(SOL))+
             (9).to_bytes(4,"little")+b"Solana   "+
             (3).to_bytes(4,"little")+b"SOL")
        result=parse_metadata(raw,SOL)
        self.assertEqual(result["symbol"],"SOL")
        with self.assertRaisesRegex(ValueError,"different mint"):
            parse_metadata(raw,USDC)
        with self.assertRaises(ValueError):
            parse_metadata(raw[:70],SOL)

    def test_retrieved_metadata_requires_actual_owner_and_mint(self):
        from solders.pubkey import Pubkey
        raw=(b"\x04"+b"\x11"*32+bytes(Pubkey.from_string(SOL))+
             (6).to_bytes(4,"little")+b"Solana"+
             (3).to_bytes(4,"little")+b"SOL")
        acct={"owner":PROGRAM,"executable":False,
              "data":[base64.b64encode(raw).decode(),"base64"]}
        with patch("arb.chain_token_pair_labels.call",
                   return_value={"value":[acct]}) as rpc:
            result=fetch_labels("rpc",[SOL])
        self.assertEqual(result["labels"][SOL]["symbol"],"SOL")
        self.assertEqual(len(rpc.call_args.args[2][0]),1)
        with patch("arb.chain_token_pair_labels.call",
                   return_value={"value":[{**acct,"owner":"fake"}]}):
            denied=fetch_labels("rpc",[SOL])
        self.assertEqual(denied["labels"],{})
        self.assertEqual(len(denied["unresolved"]),1)

    def test_graph_uses_canonical_mints_not_metadata_labels(self):
        mint="z"*44
        report={"graph_pools":[{"venue":"orca","address":"a"*44,
                                "mints":[SOL,mint],"pair":"SOL/zzzzzzzz…"}],
                "cross_venue_shared_pairs":[]}
        meta={"status":"MINT_BOUND_DISPLAY_METADATA_ONLY",
              "labels":{mint:{"mint":mint,"symbol":"TOKEN",
                "source":"METAPLEX_MINT_BOUND_SELF_DECLARED_DISPLAY_ONLY"}},
              "unresolved":[]}
        updated=annotate_report(report,meta)
        self.assertEqual(updated["graph_pools"][0]["pair"],"SOL/TOKEN")
        self.assertEqual(updated["graph_pools"][0]["mints"],[SOL,mint])

if __name__=="__main__":
    unittest.main()
