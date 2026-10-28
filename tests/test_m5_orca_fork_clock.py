import base64,unittest
from unittest.mock import patch
from arb.orca_fork_clock import fork_clock,stable_orca_fork_clock
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
SYSVAR_OWNER="Sysvar1111111111111111111111111111111111111"

class ForkClockSourceTests(unittest.TestCase):
    def response(self,ts,slot=100,*,owner=SYSVAR_OWNER):
        raw=(slot.to_bytes(8,"little")+
             (ts-1000).to_bytes(8,"little",signed=True)+
             (3).to_bytes(8,"little")+
             (3).to_bytes(8,"little")+
             ts.to_bytes(8,"little",signed=True))
        return {"value":{"owner":owner,"executable":False,
            "data":[base64.b64encode(raw).decode(),"base64"]}}
    @patch("arb.orca_fork_clock.call")
    def test_real_sysvar_binary_layout_and_clock_stability(self,call):
        call.side_effect=[self.response(1793149190,100),
                          self.response(1793149190,100)]
        before=fork_clock("http://127.0.0.1:8899")
        after=fork_clock("http://127.0.0.1:8899")
        self.assertEqual(before["fork_unix_timestamp"],1793149190)
        stable=stable_orca_fork_clock(before,after)
        self.assertTrue(stable["fork_clock_stable_for_quote"])
        self.assertEqual(stable["fork_unix_timestamp"],1793149190)
        self.assertFalse(stable["broadcast"])
    @patch("arb.orca_fork_clock.call")
    def test_fork_clock_drift_is_never_silently_priced(self,call):
        call.side_effect=[self.response(1793149190),
                          self.response(1793149191)]
        state=stable_orca_fork_clock(fork_clock("fork"),fork_clock("fork"))
        self.assertFalse(state["fork_clock_stable_for_quote"])
        self.assertIsNone(state["fork_unix_timestamp"])
    @patch("arb.orca_fork_clock.call")
    def test_wrong_owner_cannot_provide_fee_time(self,call):
        call.return_value=self.response(1793149190,owner="not sysvar")
        with self.assertRaisesRegex(ValueError,"identity"):
            fork_clock("fork")
    @patch("arb.orca_fork_clock.call")
    def test_untrusted_short_clock_rejected(self,call):
        call.return_value={"value":{"owner":SYSVAR_OWNER,"executable":False,
           "data":[base64.b64encode(b"invalid").decode(),"base64"]}}
        with self.assertRaisesRegex(ValueError,"layout"):
            fork_clock("fork")
