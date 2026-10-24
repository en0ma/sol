import unittest
from unittest.mock import patch
from arb.damm_cpmm_atomic_offline import export, run, _cpi_intermediate_flow

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
            _cpi_intermediate_flow(tx,{"innerInstructions":[]},account)

if __name__=="__main__":
    unittest.main()
