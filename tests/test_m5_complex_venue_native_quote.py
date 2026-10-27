import unittest
from unittest.mock import patch
from arb.m5_complex_venue_native_quote import quote_auxiliary

class SevenNativeVenueAuxiliaryTests(unittest.TestCase):
    def fixture(self):
        return {"state_accounts_observed_slot":123,
            "state_account_addresses":["POOL","BIN","FEE"],
            "accounts":{"POOL":{"executable":False,"data":["AA==","base64"]},"BIN":{"executable":False,"data":["AA==","base64"]},"FEE":{"executable":False,"data":["AA==","base64"]}}}
    def row(self,venue):
        state={"token_x_mint":"A","token_y_mint":"B","active_id":5,
               "token_a_mint":"A","token_b_mint":"B",
               "base_mint":"A","quote_mint":"B"}
        return {"venue":venue,"address":"POOL","mints":["A","B"],"decoded_pool_state":state}
    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_all_three_fail_closed_without_authenticated_auxiliary_decoder(self,verify):
        for venue in ("meteora_dlmm","meteora_damm_v2","pumpswap"):
            with self.subTest(venue=venue),self.assertRaisesRegex(ValueError,"MISSING_NATIVE_AUXILIARY_STATE"):
                quote_auxiliary(self.fixture(),self.row(venue),venue=venue,mint_in="A",
                    amount_in=100,auxiliary={"snapshot_slot":123,
                    "source_account_addresses":["POOL","BIN"]})
        self.assertEqual(verify.call_count,3)
    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_rejects_mismatched_slot_or_external_account(self,verify):
        for accounts,slot in ((["POOL","NOT_SOURCE"],123),(["POOL","FEE"],124)):
            with self.assertRaisesRegex(ValueError,"MISSING_NATIVE_AUXILIARY_STATE"):
                quote_auxiliary(self.fixture(),self.row("pumpswap"),
                    venue="pumpswap",mint_in="A",amount_in=100,
                    auxiliary={"snapshot_slot":slot,"source_account_addresses":accounts,
                    "native_state_decoder_authenticated":True})
    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_rejects_duplicate_and_missing_source_auxiliary_accounts(self,verify):
        fixture=self.fixture()
        for addresses in (["POOL","POOL"],["POOL","ABSENT"]):
            with self.subTest(addresses=addresses),self.assertRaisesRegex(
                    ValueError,"MISSING_NATIVE_AUXILIARY_STATE"):
                quote_auxiliary(fixture,self.row("meteora_dlmm"),
                    venue="meteora_dlmm",mint_in="A",amount_in=100,
                    auxiliary={"snapshot_slot":123,"source_account_addresses":addresses,
                        "native_state_decoder_authenticated":True})
        fixture["accounts"]["BIN"]=None
        with self.assertRaisesRegex(ValueError,"captured source account not present"):
            quote_auxiliary(fixture,self.row("meteora_dlmm"),
                venue="meteora_dlmm",mint_in="A",amount_in=100,
                auxiliary={"snapshot_slot":123,
                    "source_account_addresses":["POOL","BIN"],
                    "native_state_decoder_authenticated":True})

    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_rejects_executable_account_in_source_auxiliary_inventory(self,verify):
        fixture=self.fixture()
        fixture["accounts"]["BIN"]={"executable":True}
        with self.assertRaisesRegex(ValueError,"captured source account not present"):
            quote_auxiliary(fixture,self.row("meteora_dlmm"),
                venue="meteora_dlmm",mint_in="A",amount_in=100,
                auxiliary={"snapshot_slot":123,
                    "source_account_addresses":["POOL","BIN"],
                    "native_state_decoder_authenticated":True})

    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_rejects_source_account_without_base64_evidence(self,verify):
        fixture=self.fixture()
        fixture["accounts"]["BIN"]["data"]=["not-base64","jsonParsed"]
        with self.assertRaisesRegex(ValueError,"source bytes unavailable"):
            quote_auxiliary(fixture,self.row("meteora_dlmm"),
                venue="meteora_dlmm",mint_in="A",amount_in=100,
                auxiliary={"snapshot_slot":123,"source_account_addresses":["POOL","BIN"],
                    "native_state_decoder_authenticated":True})

    @patch("arb.m5_complex_venue_native_quote.verify")
    def test_native_dlmm_quote_requires_active_bin_and_uses_existing_math(self,verify):
        aux={"snapshot_slot":123,"source_account_addresses":["POOL","BIN"],
             "native_state_decoder_authenticated":True,"bins":[{"bin_id":5,
             "price_q64":1<<64,"amount_x":100000,"amount_y":100000}],
             "total_fee_rate":0,"swap_x_for_y":True}
        result=quote_auxiliary(self.fixture(),self.row("meteora_dlmm"),
            venue="meteora_dlmm",mint_in="A",amount_in=100,auxiliary=aux)
        self.assertEqual(result["amount_out"],100)
        self.assertFalse(result["protocol_exact_verified"])
        self.assertFalse(result["broadcast"])
        aux["bins"][0]["bin_id"]=4
        with self.assertRaisesRegex(ValueError,"active bin"):
            quote_auxiliary(self.fixture(),self.row("meteora_dlmm"),
                venue="meteora_dlmm",mint_in="A",amount_in=100,auxiliary=aux)

if __name__=="__main__":unittest.main()
