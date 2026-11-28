import importlib.util
import unittest
from unittest.mock import patch
from arb.pumpswap_signed_runner import sign_and_simulate


class Payer:
    def pubkey(self): return "user"


class PumpSwapSignedRunnerTests(unittest.TestCase):
    def pool(self):
        return {"verified":True,"canonical_pool_verified":True,"address":"pool",
                "base_mint":"base","quote_mint":"quote"}

    def test_external_rpc_denied_before_signing(self):
        with self.assertRaisesRegex(ValueError,"localhost"):
            sign_and_simulate("https://api.mainnet-beta.solana.com",
                self.pool(),Payer(),"sell",{},100,1,"base-account","quote-account",100,0)

    def test_wrong_payer_or_pool_denied(self):
        with self.assertRaisesRegex(ValueError,"identity mismatch"):
            sign_and_simulate("http://127.0.0.1:8899",self.pool(),Payer(),"sell",
                {"user":"someone-else","pool":"pool"},100,1,
                "base-account","quote-account",100,0)

    def test_inverted_token_addresses_denied(self):
        with self.assertRaisesRegex(ValueError,"direction mismatch"):
            sign_and_simulate("http://127.0.0.1:8899",self.pool(),Payer(),"sell",
                {"user":"user","pool":"pool",
                 "user_base_token_account":"base-account",
                 "user_quote_token_account":"quote-account"},100,1,
                "quote-account","base-account",100,0)

    @unittest.skipUnless(importlib.util.find_spec("solders"),
                         "solders required for signed transaction")
    def test_sell_signs_locally_and_passes_minimum_output_to_verifier(self):
        from solders.keypair import Keypair
        from solders.hash import Hash
        from arb.orca_whirlpool import b58
        payer=Keypair()
        key=lambda n:b58(bytes([n])*32)
        pool={**self.pool(),"address":key(1),"base_mint":key(2),
              "quote_mint":key(3)}
        source,dest=key(4),key(5)
        addresses={"user":str(payer.pubkey()),"pool":pool["address"],
                   "user_base_token_account":source,
                   "user_quote_token_account":dest}
        from solders.instruction import Instruction
        from solders.pubkey import Pubkey
        instruction=Instruction(Pubkey.from_string(key(6)),b"swap",[])
        with patch("arb.pumpswap_user_preflight.verify_user_accounts",
                   return_value={"user_accounts_verified":True}) as preflight:
            with patch("arb.pumpswap_signed_runner.build_instruction",
                       return_value=instruction) as builder:
                with patch("arb.rpc.call",return_value={
                        "value":{"blockhash":str(Hash.default())}}):
                    with patch("arb.pumpswap_signed_runner.simulate_signed",
                               return_value={"simulation_verified":True}) as simulate:
                        result=sign_and_simulate(
                            "http://127.0.0.1:8899",pool,payer,"sell",
                            addresses,100,22,source,dest,200,0)
        self.assertEqual(preflight.call_count,1)
        self.assertEqual(builder.call_count,1)
        self.assertEqual(simulate.call_count,1)
        self.assertEqual(simulate.call_args.kwargs["min_amount_out"],22)
        self.assertEqual(simulate.call_args.args[6:9],(200,0,100))
        self.assertTrue(result["local_only"])
        self.assertFalse(result["quote_reconciled"])
        self.assertFalse(result["fee_mode_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["live_execution_approved"])
        self.assertFalse(result["broadcast"])
        self.assertGreater(result["transaction_bytes"],0)

    def test_unverified_pool_rejected_before_account_preflight(self):
        with patch("arb.pumpswap_user_preflight.verify_user_accounts") as preflight:
            with self.assertRaisesRegex(ValueError,"unverified"):
                sign_and_simulate("http://127.0.0.1:8899",
                    {**self.pool(),"verified":False},Payer(),"sell",
                    {},100,1,"base-account","quote-account",100,0)
            preflight.assert_not_called()
