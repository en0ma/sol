"""A missing DLMM source bin is never fabricated by bounded read rechecks."""
import base64
import unittest
from unittest.mock import patch
from arb.next_ten_pair_fixture_export import venue_accounts


POOL="source-dlmm-pool"
X="x-mint"
Y="y-mint"
STATE={"reserve_x":"source-x-reserve","reserve_y":"source-y-reserve",
       "oracle":"source-oracle","token_x_mint":X,"token_y_mint":Y}


def preflight(status):
    return {"status":status,"active_bin_array_index":-4,
            "active_bin_array_pda":"active-bin",
            "neighboring_bin_arrays":[{"pda":"active-bin","authenticated":True}]}


class DlmmSourceActiveRecheckTests(unittest.TestCase):
    def do_capture(self, side_effect):
        with patch("arb.next_ten_fork_pool_probe.snapshot",
                   return_value={"mints":[X,Y]}), patch(
            "arb.next_ten_pair_fixture_export._fetch",
            return_value={POOL:{"data":[base64.b64encode(b"source").decode()]}}
        ), patch("arb.meteora_dlmm.decode",return_value=STATE), patch(
            "arb.meteora_dlmm_bin_preflight.check_active_bin_array",
            side_effect=side_effect
        ) as checks, patch(
            "arb.meteora_dlmm_bin_preflight.inspect_directional_bin_arrays",
            return_value={"bin_arrays":["active-bin"],"source_authenticated":True}
        ):
            try:
                capture=venue_accounts("http://127.0.0.1:8899",
                                       "meteora_dlmm",POOL,[X,Y],
                                       directional_only=True)
                return capture,checks.call_count,None
            except ValueError as error:
                return None,checks.call_count,str(error)

    def test_accepts_only_fresh_authenticated_active_source(self):
        capture,count,error=self.do_capture([
            preflight("ACTIVE_BIN_ARRAY_ABSENT"),
            preflight("ACTIVE_BIN_ARRAY_ABSENT"),
            preflight("ACTIVE_BIN_ARRAY_AUTHENTICATED")])
        self.assertIsNone(error)
        self.assertEqual(count,3)
        extra,proof=capture
        self.assertIn("active-bin",extra)
        self.assertEqual(proof["bin_preflight"]["status"],
                         "ACTIVE_BIN_ARRAY_AUTHENTICATED")

    def test_persistently_absent_active_array_stays_blocked(self):
        capture,count,error=self.do_capture([
            preflight("ACTIVE_BIN_ARRAY_ABSENT")]*3)
        self.assertIsNone(capture)
        self.assertEqual(count,3)
        self.assertIn("ACTIVE_BIN_ARRAY_ABSENT",error)
        self.assertIn(POOL,error)
        self.assertIn("active-bin",error)

    def test_other_source_failure_is_not_retried(self):
        capture,count,error=self.do_capture([
            preflight("UNSUPPORTED_LAYOUT")])
        self.assertIsNone(capture)
        self.assertEqual(count,1)
        self.assertIn("UNSUPPORTED_LAYOUT",error)


if __name__=="__main__":
    unittest.main()
