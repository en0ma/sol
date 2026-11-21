"""Directional DLMM source authentication does not rely on stale preflight."""
import base64
import unittest
from unittest.mock import patch
from arb.next_ten_pair_fixture_export import venue_accounts


POOL="source-dlmm-pool"
X="x-mint"
Y="y-mint"
STATE={"active_id":-281,"reserve_x":"source-x-reserve","reserve_y":"source-y-reserve",
       "oracle":"source-oracle","token_x_mint":X,"token_y_mint":Y}


class DlmmDirectionalSourceTests(unittest.TestCase):
    def do_capture(self, direction):
        with patch("arb.next_ten_fork_pool_probe.snapshot",
                   return_value={"mints":[X,Y]}), patch(
            "arb.next_ten_pair_fixture_export._fetch",
            return_value={POOL:{"data":[base64.b64encode(b"source").decode()]}}
        ), patch("arb.meteora_dlmm.decode",return_value=STATE), patch(
            "arb.meteora_dlmm_bin_preflight.check_active_bin_array",
            side_effect=AssertionError("stale preflight forbidden")
        ) as stale, patch(
            "arb.meteora_dlmm_bin_preflight.verify_pool_oracle",
            return_value={"oracle":STATE["oracle"],"authenticated":True}
        ) as oracle, patch(
            "arb.meteora_dlmm_bin_preflight.inspect_directional_bin_arrays",
            side_effect=direction
        ) as inspector:
            try:
                captured=venue_accounts("http://127.0.0.1:8899",
                                        "meteora_dlmm",POOL,[X,Y],
                                        directional_only=True)
                return captured,stale.call_count,oracle.call_count,inspector.call_args_list,None
            except ValueError as error:
                return None,stale.call_count,oracle.call_count,inspector.call_args_list,str(error)

    def test_authenticates_from_source_pool_active_id_and_direction(self):
        result,stale,oracle,calls,error=self.do_capture([{
            "bin_arrays":["actual-active-bin"],"source_authenticated":True,
            "source_context_slot":42}])
        self.assertIsNone(error)
        self.assertEqual((stale,oracle),(0,1))
        self.assertEqual(calls[0].kwargs["input_is_x"],True)
        self.assertEqual(calls[0].args[2],-5)
        extra,proof=result
        self.assertIn("actual-active-bin",extra)
        self.assertEqual(proof["active_bin_array_index"],-5)
        self.assertEqual(proof["bin_preflight"]["status"],
                         "DIRECTIONAL_SOURCE_ACTIVE_ARRAY_AUTHENTICATED")

    def test_missing_source_active_array_is_hard_rejection(self):
        # Without a genuinely authenticated fallback, the absent active PDA
        # cannot enter the signed route.
        with self.assertRaises(AssertionError):
            self.do_capture([
                ValueError("DLMM active directional bin array absent")])

    def test_missing_directional_active_can_use_real_legacy_preflight(self):
        source={"status":"ACTIVE_BIN_ARRAY_AUTHENTICATED",
                "active_bin_array_index":-5,
                "neighboring_bin_arrays":[
                    {"pda":"left-bin","authenticated":True},
                    {"pda":"active-bin","authenticated":True},
                    {"pda":"right-bin","authenticated":True}]}
        with patch("arb.next_ten_fork_pool_probe.snapshot",
                   return_value={"mints":[X,Y]}), patch(
            "arb.next_ten_pair_fixture_export._fetch",
            return_value={POOL:{"data":[base64.b64encode(b"source").decode()]}}
        ), patch("arb.meteora_dlmm.decode",return_value=STATE), patch(
            "arb.meteora_dlmm_bin_preflight.inspect_directional_bin_arrays",
            side_effect=ValueError("DLMM active directional bin array absent")
        ), patch("arb.meteora_dlmm_bin_preflight.check_active_bin_array",
                 return_value=source) as preflight:
            extras,evidence=venue_accounts("http://127.0.0.1:8899",
                                           "meteora_dlmm",POOL,[X,Y],
                                           directional_only=True)
        preflight.assert_called_once()
        self.assertEqual(evidence["bin_arrays"],
                         ["left-bin","active-bin","right-bin"])
        self.assertIsNone(evidence["directional_bin_source"])
        self.assertEqual(
            evidence["bin_preflight"]["directional_fallback_status"],
            "AUTHENTICATED_LEGACY_THREE_ARRAYS")

    def test_wrong_active_index_remains_hard_rejection(self):
        with patch("arb.next_ten_fork_pool_probe.snapshot",
                   return_value={"mints":[X,Y]}), patch(
            "arb.next_ten_pair_fixture_export._fetch",
            return_value={POOL:{"data":[base64.b64encode(b"source").decode()]}}
        ), patch("arb.meteora_dlmm.decode",return_value=STATE), patch(
            "arb.meteora_dlmm_bin_preflight.inspect_directional_bin_arrays",
            side_effect=ValueError("DLMM active directional bin array absent")
        ), patch("arb.meteora_dlmm_bin_preflight.check_active_bin_array",
            return_value={"status":"ACTIVE_BIN_ARRAY_AUTHENTICATED",
                          "active_bin_array_index":-4}):
            with self.assertRaisesRegex(ValueError,
                                        "directional and legacy"):
                venue_accounts("http://127.0.0.1:8899",
                               "meteora_dlmm",POOL,[X,Y],
                               directional_only=True)

    def test_wrong_owner_is_not_recovered_by_preflight(self):
        result,stale,oracle,calls,error=self.do_capture([
            ValueError("directional DLMM bin array owner mismatch")])
        self.assertIsNone(result)
        self.assertEqual(stale,0)
        self.assertEqual(len(calls),1)
        self.assertIn("owner mismatch",error)


if __name__=="__main__":
    unittest.main()
