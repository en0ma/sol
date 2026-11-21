"""Fail-closed source bytes reveal Orca A->B liquidity cliffs, not quotes."""
import base64
import unittest
from unittest.mock import patch

from arb.orca_whirlpool import DISCRIMINATOR as POOL_DISC, PROGRAM, b58
from arb.whirlpool_ticks import DISC as TICK_DISC, FIXED_LEN, authenticated_downward_liquidity_cliff


class SourceAuthenticatedOrcaCliffTests(unittest.TestCase):
    def setup_fixture(self, *, net=1293927, include_lower=False,
                      a_to_b=True, tamper_owner=False):
        pool_bytes=bytes([3])*32
        pool=b58(pool_bytes)
        mint_a=b58(bytes([1])*32)
        mint_b=b58(bytes([2])*32)
        tick=-32255
        spacing=128
        first=-33792
        addresses=["array0","array1","array2"]
        raw=bytearray(653)
        raw[:8]=POOL_DISC
        raw[41:43]=spacing.to_bytes(2,"little")
        raw[49:65]=(1293927).to_bytes(16,"little")
        raw[65:81]=(3677581428353834781).to_bytes(16,"little")
        raw[81:85]=tick.to_bytes(4,"little",signed=True)
        raw[101:133]=bytes([1])*32
        raw[181:213]=bytes([2])*32

        def account(data,owner=PROGRAM):
            return {"owner":owner,"executable":False,
                    "data":[base64.b64encode(data).decode(),"base64"]}

        accounts={pool:account(raw)}
        for address,start in zip(addresses,[first,first-88*spacing,first-2*88*spacing]):
            buf=bytearray(FIXED_LEN)
            buf[:8]=TICK_DISC
            buf[8:12]=start.to_bytes(4,"little",signed=True)
            buf[-32:]=pool_bytes
            if start==first:
                boundary=-32256
                i=(boundary-first)//spacing
                offset=12+i*113
                buf[offset]=1
                buf[offset+1:offset+17]=net.to_bytes(16,"little",signed=True)
                buf[offset+17:offset+33]=(1293927).to_bytes(16,"little")
                if include_lower:
                    j=(boundary-spacing-first)//spacing
                    pos=12+j*113
                    buf[pos]=1
                    buf[pos+1:pos+17]=(100).to_bytes(16,"little",signed=True)
                    buf[pos+17:pos+33]=(100).to_bytes(16,"little")
            accounts[address]=account(
                buf,owner=("invalid-owner" if tamper_owner and start==first else PROGRAM))
        fixture={
            "route_venues":["orca"],
            "route_pool_addresses":[pool],
            "route_mints":[mint_a if a_to_b else mint_b,mint_b if a_to_b else mint_a],
            "leg_evidence_by_index":[{"pool":pool,"venue":"orca",
                "auxiliary":{"tick_arrays":addresses}}],
            "accounts":accounts,
        }
        return fixture,addresses

    def audit(self,fixture,addresses):
        with patch("arb.source_snapshot_manifest.verify"), patch(
                "arb.whirlpool_swap.select_tick_arrays",return_value=addresses):
            return authenticated_downward_liquidity_cliff(fixture,0)

    def test_zero_liquidity_after_first_tick_is_only_diagnostic(self):
        fixture,addresses=self.setup_fixture()
        report=self.audit(fixture,addresses)
        self.assertEqual(
            report["status"],
            "SOURCE_AUTHENTICATED_FIRST_DOWNWARD_TICK_DEPLETES_LIQUIDITY")
        self.assertEqual(report["first_downward_initialized_tick"],-32256)
        self.assertEqual(report["liquidity_after_first_crossing"],"0")
        self.assertFalse(report["causes_6038_proven"])
        self.assertFalse(report["executable_quote_verified"])
        self.assertFalse(report["actionable"])
        self.assertFalse(report["broadcast"])

    def test_remaining_liquidity_is_not_misclassified(self):
        fixture,addresses=self.setup_fixture(net=100)
        self.assertIsNone(self.audit(fixture,addresses))

    def test_initialized_tick_below_boundary_is_not_misclassified(self):
        fixture,addresses=self.setup_fixture(include_lower=True)
        self.assertIsNone(self.audit(fixture,addresses))

    def test_reverse_direction_not_misclassified(self):
        fixture,addresses=self.setup_fixture(a_to_b=False)
        self.assertIsNone(self.audit(fixture,addresses))

    def test_wrong_account_owner_is_rejected(self):
        fixture,addresses=self.setup_fixture(tamper_owner=True)
        with self.assertRaisesRegex(ValueError,"unauthenticated"):
            self.audit(fixture,addresses)

    def test_missing_or_swapped_tick_evidence_is_rejected(self):
        fixture,addresses=self.setup_fixture()
        fixture["leg_evidence_by_index"][0]["auxiliary"]["tick_arrays"]=[
            "not-source-captured",*addresses[:2]]
        with self.assertRaisesRegex(ValueError,"directional source tick evidence"):
            self.audit(fixture,addresses)

    def test_manifest_verification_cannot_be_bypassed(self):
        fixture,addresses=self.setup_fixture()
        with patch("arb.source_snapshot_manifest.verify",
                   side_effect=ValueError("tampered manifest")), patch(
                   "arb.whirlpool_swap.select_tick_arrays",return_value=addresses):
            with self.assertRaisesRegex(ValueError,"tampered manifest"):
                authenticated_downward_liquidity_cliff(fixture,0)


if __name__=="__main__":
    unittest.main()
