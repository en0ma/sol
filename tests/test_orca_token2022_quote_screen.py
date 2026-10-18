import unittest
from unittest.mock import patch
from arb.orca_token2022_quote_screen import screen, diagnostic_failure_category, screen_with_rate_limit_retry, simple_mint_extension_candidates, validate_directional_snapshot_accounts

A="So11111111111111111111111111111111111111112"
B="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
POOL="7qbRF6YsyGuLUVs6Y1q64bdVrfe4ZcUUz1JRdoVNUJnm"
STATE={"token_mint_a":A,"token_mint_b":B,"token_vault_a":"vault-A","token_vault_b":"vault-B"}
def observed():
    cfg={"older":{"epoch":0,"basis_points":100,"maximum_fee":1000},
         "newer":{"epoch":4,"basis_points":200,"maximum_fee":1000}}
    return {"pool":STATE,"slot":12,"mints":[A,B],
            "vault_accounts":[{"mint":A,"state":1},{"mint":B,"state":1}],
            "mint_accounts":[{"transfer_fee_config":cfg,"owner":"TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb","extension_types":[1,14]},
                             {"transfer_fee_config":cfg,"owner":"TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb","extension_types":[1]}],
            "epoch_observation":{"epoch":4},
            "extension_risk":{"blocking_extension_ids":[1]}}
class QuoteScreenTests(unittest.TestCase):
    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_fees_use_single_snapshot_tick_arrays(self,snap,quote):
        state=observed()
        state["tick_arrays"]=[{"start_tick":0,"status":"FIXED_VALID","ticks":[]}]
        snap.return_value=state
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        result=screen("rpc",POOL,A,101)
        self.assertEqual(result["pool_net_input_base_units"],98)
        self.assertEqual(result["recipient_net_output_base_units"],98)
        self.assertIs(quote.call_args.args[3],state["tick_arrays"])
        snap.assert_called_once_with("rpc",POOL,include_ticks=True,include_oracle=True)
        self.assertFalse(result["actionable"])
        self.assertEqual(result["swap_account_candidates"]["input_mint"],A)
        self.assertFalse(result["swap_account_candidates"]["instruction_account_metas_verified"])
        from solders.pubkey import Pubkey
        from arb.orca_whirlpool import PROGRAM
        oracle=str(Pubkey.find_program_address([b"oracle",bytes(Pubkey.from_string(POOL))],Pubkey.from_string(PROGRAM))[0])
        self.assertEqual(result["swap_account_candidates"]["oracle_pda_candidate"],oracle)
        self.assertFalse(result["swap_account_candidates"]["oracle_account_verified"])
        self.assertIsNone(result["swap_account_candidates"]["oracle_same_slot_evidence"])
        self.assertFalse(result["swap_account_candidates"]["remaining_accounts_verified"])
        for requirement in ("swap_v2_user_token_accounts_verified","swap_v2_authority_verified","swap_v2_oracle_verified","swap_v2_tick_order_verified"):
            self.assertIs(result["swap_account_candidates"][requirement],False)
        self.assertEqual(result["swap_account_candidates"]["tick_array_accounts_present"],1)
        self.assertEqual(result["swap_account_candidates"]["tick_array_statuses"],["FIXED_VALID"])
        self.assertIn("MINT_EXTENSION_1_UNSUPPORTED_FOR_EXECUTION",result["execution_blockers"])
        self.assertIn("SIGNED_ATOMIC_SIMULATION_NOT_VERIFIED",result["execution_blockers"])
        self.assertIn("SWAP_ACCOUNT_METAS_NOT_VERIFIED",result["execution_blockers"])
        self.assertNotIn("TRANSFER_HOOK_ACCOUNTS_NOT_VERIFIED",result["execution_blockers"])
        self.assertEqual(len(result["mint_execution_evidence"]),2)
        self.assertTrue(result["mint_execution_evidence"][0]["transfer_hook_extension_present"])
        self.assertEqual(result["mint_execution_evidence"][0]["transfer_hook_configuration_status"],"EXTENSION_PRESENT_NO_ACTIVE_PROGRAM")
        self.assertEqual(result["mint_execution_evidence"][1]["transfer_hook_configuration_status"],"NO_HOOK_EXTENSION")
        self.assertFalse(result["mint_execution_evidence"][0]["transfer_hook_extra_accounts_verified"])
        self.assertFalse(result["mint_execution_evidence"][1]["swap_account_metas_verified"])
        self.assertFalse(result["mint_execution_evidence"][0]["transfer_hook_program_identity_observed"])

    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_configured_hook_keeps_extra_account_blocker(self,snap,quote):
        state=observed()
        state["tick_arrays"]=[{"status":"FIXED_VALID"}]
        state["mint_accounts"][0]["transfer_hook_program_id"]="HookProgramID"
        snap.return_value=state
        quote.return_value={"estimated_output_base_units":100,
                            "tick_arrays_examined":1,"ticks_crossed":0}
        result=screen("rpc",POOL,A,101)
        self.assertIn("TRANSFER_HOOK_ACCOUNTS_NOT_VERIFIED",result["execution_blockers"])
        self.assertEqual(result["mint_execution_evidence"][0]["transfer_hook_configuration_status"],
                         "PROGRAM_CONFIGURED")
        self.assertFalse(result["executable_quote"])

    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_missing_synchronized_ticks_fails_closed(self,snap):
        snap.return_value={**observed(),"tick_arrays":[]}
        with self.assertRaisesRegex(ValueError,"synchronized"):
            screen("rpc",POOL,A,100)

    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_default_direction(self,snap,quote):
        snap.return_value={**observed(),"tick_arrays":[{"status":"FIXED_VALID"}]}
        quote.return_value={"estimated_output_base_units":100,"tick_arrays_examined":1,"ticks_crossed":0}
        self.assertEqual(screen("rpc",POOL,None,101)["input_mint"],A)

    @patch("arb.orca_token2022_quote_screen.quote_from_decoded_arrays")
    @patch("arb.orca_token2022_quote_screen.scheduled_epoch_snapshot")
    def test_missing_tick_coverage_reports_array_statuses(self,snap,quote):
        state=observed()
        state["pool"]={**STATE,"tick_current_index":5,"tick_spacing":1}
        state["tick_arrays"]=[{"start_tick":0,"address":"missing-current-array-pda","status":"MISSING"}]
        snap.return_value=state
        quote.side_effect=ValueError("missing or unsupported tick array")
        with self.assertRaisesRegex(ValueError,"current_start=0") as result:
            screen("rpc",POOL,A,101)
        self.assertIn("MISSING",str(result.exception))
        self.assertIn("missing-current-array-pda",str(result.exception))
        self.assertIn("tick_spacing=1",str(result.exception))

class QuoteFailureCategoryTests(unittest.TestCase):
    def test_epoch_and_tick_mismatches_stay_distinct(self):
        self.assertEqual(diagnostic_failure_category(
            "epoch observations do not bracket pool snapshot: before_slot=12 snapshot_slot=11"),
            "EPOCH_OR_POOL_SLOT_MISMATCH")
        self.assertEqual(diagnostic_failure_category(
            "tick arrays and mint/vault snapshot are not same-slot: mint_vault_slot=12 tick_slot=13"),
            "TICK_SLOT_MISMATCH")
        self.assertEqual(diagnostic_failure_category("upstream RPC 429 Too Many Requests"),
                         "UPSTREAM_RATE_LIMIT")
        self.assertEqual(diagnostic_failure_category(
            "missing tick coverage: current_start=1144 direction=a_to_b "
            "array_statuses=[{'start_tick': 1144, 'status': 'MISSING'}]"),
            "CURRENT_OR_DIRECTIONAL_TICK_ARRAY_MISSING")
        self.assertEqual(diagnostic_failure_category(
            "ValueError: missing tick coverage: current_tick=1160 tick_spacing=1 "
            "current_start=1144 direction=a_to_b array_statuses="
            "[{'start_tick': 1144, 'address': '44Zh7USf', 'status': 'MISSING'}]"),
            "CURRENT_OR_DIRECTIONAL_TICK_ARRAY_MISSING")
        self.assertEqual(diagnostic_failure_category("unknown failure"),"OTHER_UNQUOTABLE")

class ThrottleRetryTests(unittest.TestCase):
    @patch("arb.orca_token2022_quote_screen.screen")
    def test_retry_is_new_complete_snapshot(self,mocked):
        mocked.side_effect=[RuntimeError("429 Too Many Requests"),
                            {"status":"INDICATIVE_TOKEN2022_QUOTE_ONLY"}]
        delays=[]
        result=screen_with_rate_limit_retry("rpc",POOL,None,100,sleeper=delays.append)
        self.assertEqual(result["status"],"INDICATIVE_TOKEN2022_QUOTE_ONLY")
        self.assertEqual(mocked.call_count,2)
        self.assertEqual(delays,[1.5])

    @patch("arb.orca_token2022_quote_screen.screen")
    def test_missing_tick_array_is_never_retried(self,mocked):
        mocked.side_effect=ValueError("missing tick coverage")
        delays=[]
        with self.assertRaisesRegex(ValueError,"missing tick coverage"):
            screen_with_rate_limit_retry("rpc",POOL,None,100,sleeper=delays.append)
        self.assertEqual(mocked.call_count,1)
        self.assertEqual(delays,[])

    @patch("arb.orca_token2022_quote_screen.screen")
    def test_throttling_exhaustion_stays_unquotable(self,mocked):
        mocked.side_effect=RuntimeError("HTTP 429 Too Many Requests")
        delays=[]
        with self.assertRaisesRegex(RuntimeError,"429"):
            screen_with_rate_limit_retry("rpc",POOL,None,100,sleeper=delays.append)
        self.assertEqual(mocked.call_count,3)
        self.assertEqual(delays,[1.5,3.0])

class HookProgramParsingTests(unittest.TestCase):
    def test_hook_program_id_parsed_from_mint_tlv(self):
        from arb.token2022_extensions import transfer_hook_program_id
        from arb.orca_whirlpool import b58
        base=bytearray(166)
        base[165]=1
        raw=bytes(base)+(14).to_bytes(2,"little")+(64).to_bytes(2,"little")+bytes(32)+bytes([7])*32
        self.assertEqual(transfer_hook_program_id(raw),b58(bytes([7])*32))

    def test_absent_or_malformed_hook_is_not_authorized(self):
        from arb.token2022_extensions import transfer_hook_program_id
        base=bytearray(166)
        base[165]=1
        self.assertIsNone(transfer_hook_program_id(bytes(base)))
        bad=bytes(base)+(14).to_bytes(2,"little")+(63).to_bytes(2,"little")+bytes(63)
        with self.assertRaisesRegex(ValueError,"length"):
            transfer_hook_program_id(bad)

class LowExtensionRiskShortlistTests(unittest.TestCase):
    def test_shortlist_requires_all_nonexecution_gates(self):
        row={"pool":POOL,"slot":42,"input_mint":A,"output_mint":B,
             "mint_execution_evidence":[{"mint":A,"token_program":"TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"},{"mint":B,"token_program":"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"}],
             "status":"INDICATIVE_TOKEN2022_QUOTE_ONLY",
             "actionable":False,"executable_quote":False,
             "extension_risk":{"blocking_extension_ids":[]},
             "execution_blockers":["SWAP_ACCOUNT_METAS_NOT_VERIFIED",
                                   "SIGNED_ATOMIC_SIMULATION_NOT_VERIFIED"]}
        row["swap_account_candidates"]={"oracle_account_verified":True}
        self.assertEqual(simple_mint_extension_candidates([{**row,"swap_account_candidates":{"oracle_account_verified":False}}]),[])
        selected=simple_mint_extension_candidates([row])
        self.assertEqual(len(selected),1)
        self.assertEqual(selected[0]["input_token_program"],"TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
        self.assertEqual(selected[0]["output_token_program"],"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        reverse=simple_mint_extension_candidates([{**row,"input_mint":B,"output_mint":A}])
        self.assertEqual(reverse[0]["input_token_program"],"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
        self.assertFalse(selected[0]["actionable"])
        self.assertFalse(selected[0]["executable_quote"])
        self.assertFalse(selected[0]["simulation_verified"])
        self.assertEqual(simple_mint_extension_candidates([
            {**row,"extension_risk":{"blocking_extension_ids":[14]}}]),[])
        self.assertEqual(simple_mint_extension_candidates([
            {**row,"execution_blockers":[]}]),[])
        self.assertEqual(simple_mint_extension_candidates([
            {**row,"executable_quote":True}]),[])

class DirectionalAccountEvidenceTests(unittest.TestCase):
    def test_vaults_and_programs_follow_swap_direction(self):
        snap=observed()
        forward=validate_directional_snapshot_accounts(snap,A)
        reverse=validate_directional_snapshot_accounts(snap,B)
        self.assertEqual(forward["input_vault"],"vault-A")
        self.assertEqual(reverse["input_vault"],"vault-B")
        self.assertTrue(forward["vault_mint_relationships_verified"])
        self.assertFalse(forward["instruction_account_metas_verified"])

    def test_wrong_vault_mint_fails_closed(self):
        snap=observed()
        snap["vault_accounts"][0]["mint"]=B
        with self.assertRaisesRegex(ValueError,"mismatch"):
            validate_directional_snapshot_accounts(snap,A)
