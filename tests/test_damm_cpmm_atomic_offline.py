import unittest
from unittest.mock import patch
from arb.damm_cpmm_atomic_offline import export, run, _cpi_intermediate_flow, _post, _decode_base58, _inner_token_transfer, _top_level_venue_events

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
        self.assertIsNone(_cpi_intermediate_flow(tx,{"innerInstructions":[]},account,1000))

    def test_nested_damm_reentry_does_not_false_fail_atomic_order(self):
        from arb.damm_cpmm_atomic_offline import DAMM, CPMM
        logs=[
            f"Program {DAMM} invoke [1]",
            f"Program {DAMM} invoke [2]",
            f"Program {DAMM} success",
            f"Program {DAMM} success",
            f"Program {CPMM} invoke [1]",
            f"Program {CPMM} success",
        ]
        self.assertEqual(_top_level_venue_events(logs),[
            [DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"success"]])

    def test_negative_second_leg_failure_is_visible_at_top_level(self):
        from arb.damm_cpmm_atomic_offline import DAMM, CPMM
        logs=[f"Program {DAMM} invoke [1]",f"Program {DAMM} success",
              f"Program {CPMM} invoke [1]",
              f"Program {CPMM} failed: custom program error: 0x1"]
        self.assertEqual(_top_level_venue_events(logs),[
            [DAMM,"invoke"],[DAMM,"success"],[CPMM,"invoke"],[CPMM,"failed"]])

    def test_mismatched_nested_stack_fails_closed(self):
        from arb.damm_cpmm_atomic_offline import DAMM, CPMM
        logs=[f"Program {DAMM} invoke [1]",f"Program {CPMM} success"]
        self.assertEqual(_top_level_venue_events(logs),[])

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
            return "1"*(len(raw)-len(raw.lstrip(bytes([0]))))+(chars or "")
        data=bytes([12])+(1000).to_bytes(8,"little")+bytes([6])
        event={"programIdIndex":0,"accounts":[1,2,3,4],"data":b58(data)}
        self.assertEqual(_inner_token_transfer(event,keys,0),(str(keys[1]),str(keys[3]),1000))

    def test_parsed_transfer_checked_uses_base_units(self):
        from arb.token_vaults import TOKEN_PROGRAM
        entry={"programId":TOKEN_PROGRAM,"parsed":{"type":"transferChecked",
            "info":{"source":"source","destination":"intermediate",
                    "tokenAmount":{"amount":"10211913","decimals":6,
                                   "uiAmountString":"10.211913"}}}}
        self.assertEqual(_inner_token_transfer(entry,[],0),
                         ("source","intermediate",10211913))

    def test_parsed_transfer_checked_rejects_ui_amount(self):
        from arb.token_vaults import TOKEN_PROGRAM
        entry={"programId":TOKEN_PROGRAM,"parsed":{"type":"transferChecked",
            "info":{"source":"source","destination":"intermediate",
                    "tokenAmount":{"uiAmountString":"10.211913"}}}}
        self.assertIsNone(_inner_token_transfer(entry,[],0))

    def test_parsed_transfer_checked_rejects_foreign_program(self):
        entry={"programId":"untrusted","parsed":{"type":"transferChecked",
            "info":{"source":"source","destination":"intermediate",
                    "tokenAmount":{"amount":"1000"}}}}
        self.assertIsNone(_inner_token_transfer(entry,[],0))

    def test_real_surfpool_parsed_inner_cpi_flow_reconciles(self):
        from solders.keypair import Keypair
        from solders.hash import Hash
        from solders.instruction import Instruction,AccountMeta
        from solders.pubkey import Pubkey
        from solders.transaction import Transaction
        from arb.damm_cpmm_atomic_offline import DAMM, CPMM
        from arb.token_vaults import TOKEN_PROGRAM
        signer=Keypair()
        intermediate=str(Keypair().pubkey())
        def ix(program):
            return Instruction(Pubkey.from_string(program),b"",
                               [AccountMeta(Pubkey.from_string(intermediate),False,True)])
        tx=Transaction.new_signed_with_payer(
            [ix(DAMM),ix(CPMM)],signer.pubkey(),[signer],Hash.default())
        def transfer(source,destination,amount):
            return {"programId":TOKEN_PROGRAM,
                    "parsed":{"type":"transferChecked",
                              "info":{"source":source,"destination":destination,
                                      "tokenAmount":{"amount":str(amount)}}}}
        result={"innerInstructions":[
            {"index":0,"instructions":[transfer("vault",intermediate,10211913)]},
            {"index":1,"instructions":[transfer(intermediate,"vault2",1000)]}]}
        self.assertEqual(_cpi_intermediate_flow(tx,result,intermediate,1000),
                         {"first_leg_intermediate_received_base_units":10211913,
                          "second_leg_intermediate_consumed_base_units":1000})

    def test_invalid_base58_data_rejected(self):
        with self.assertRaises(ValueError):
            _decode_base58("0-invalid")

if __name__=="__main__":
    unittest.main()
