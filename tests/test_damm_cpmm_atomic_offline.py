import unittest
from unittest.mock import patch
from arb.damm_cpmm_atomic_offline import export, run, _cpi_intermediate_flow, _post, _decode_base58, _inner_token_transfer

class AtomicIntegrationSafety(unittest.TestCase):
    def test_source_export_refuses_remote_endpoint_before_rpc(self):
        with patch("arb.damm_cpmm_atomic_offline.call") as call:
            with self.assertRaises(ValueError):
                export("https://api.mainnet-beta.solana.com","/dev/null")
            call.assert_not_called()

    def test_execution_refuses_remote_endpoint_before_hydration(self):
        with patch("arb.damm_cpmm_atomic_offline.call") as call:
            with self.assertRaises(ValueError):
                run("https://api.mainnet-beta.solana.com",{})
            call.assert_not_called()

    def test_offline_optin_required_without_writing_accounts(self):
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"0"}):
            with patch("arb.damm_cpmm_atomic_offline.call") as call:
                with self.assertRaisesRegex(ValueError,"isolated offline"):
                    run("http://localhost:8899",{})
                call.assert_not_called()

    def test_untrusted_fixture_rejected_before_any_synthetic_write(self):
        with patch.dict("os.environ",{"SURFPOOL_EXPLICITLY_OFFLINE":"1"}):
            with patch("arb.damm_cpmm_atomic_offline.call") as call:
                with self.assertRaisesRegex(ValueError,"untrusted atomic fixture"):
                    run("http://localhost:8899",{"source":"UNKNOWN"})
                call.assert_not_called()

    def test_cpi_proof_rejects_missing_inner_instructions(self):
        from solders.keypair import Keypair
        from solders.pubkey import Pubkey
        from solders.instruction import Instruction
        from solders.transaction import Transaction
        from solders.hash import Hash
        token="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
        k=Keypair()
        account=str(Keypair().pubkey())
        # Signed message with no intermediate SPL-token account must fail.
        tx=Transaction.new_signed_with_payer(
            [Instruction(Pubkey.from_string(token),b"",[])],
            k.pubkey(),[k],Hash.default())
        with self.assertRaises(ValueError):
            _cpi_intermediate_flow(tx,{"innerInstructions":[]},account,1000)

    def test_three_token_account_snapshot_requires_three_accounts(self):
        with patch("arb.damm_cpmm_atomic_offline.call",
                   return_value={"context":{"slot":1},"value":[None,None]}):
            with self.assertRaisesRegex(ValueError,"three-account"):
                _post("http://localhost:8899",["a","b","c"],["x","y","z"],"owner")

    def test_cpi_decoder_distinguishes_transfer_checked_destination(self):
        from solders.pubkey import Pubkey
        from solders.keypair import Keypair
        from arb.token_vaults import TOKEN_PROGRAM
        keys=[Pubkey.from_string(TOKEN_PROGRAM)]+[Keypair().pubkey() for _ in range(4)]
        def b58(raw):
            alphabet="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
            n=int.from_bytes(raw,"big")
            chars=""
            while n:
                n,r=divmod(n,58)
                chars=alphabet[r]+chars
            return "1"*(len(raw)-len(raw.lstrip(b"\\x00")))+(chars or "")
        data=bytes([12])+(1000).to_bytes(8,"little")+bytes([6])
        event={"programIdIndex":0,"accounts":[1,2,3,4],"data":b58(data)}
        self.assertEqual(_inner_token_transfer(event,keys,0),(1,3,1000))

    def test_invalid_base58_data_rejected(self):
        with self.assertRaises(ValueError):
            _decode_base58("0-invalid")

if __name__=="__main__":
    unittest.main()
