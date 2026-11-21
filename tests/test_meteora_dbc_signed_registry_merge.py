"""DBC registry admission must reject unaudited CI and duplicate identities."""
import unittest
from unittest.mock import patch
from arb.meteora_dbc_signed_registry_merge import merge


class DbCRegistrySafetyTests(unittest.TestCase):
    def test_original_unsigned_source_never_admitted(self):
        registry={"pools":[]}
        with self.assertRaisesRegex(ValueError,"prerequisite"):
            merge(registry,{}, {}, {}, {},required=1)
        self.assertEqual(registry,{"pools":[]})

    def test_shared_registry_duplicate_identity_fails_before_insertion(self):
        registry={"pools":[{"venue":"orca","address":"duplicate"},
                           {"venue":"orca","address":"duplicate"}]}
        with self.assertRaises(ValueError):
            merge(registry,{}, {}, {}, {},required=1)


    def test_only_vault_audited_pool_can_stage_nonusable_identity(self):
        addr="DBC-original"
        source={"source_pools":[{"pool":addr,"source_slot":42,
             "accounts":{addr:{"sha256":"a"*64}},
             "pool_fields":{"base_mint":"mint-a","quote_mint":"mint-b"}}]}
        accepted={"independently_signed_verified_pools":1,
                  "all_source_vault_poststates_reconciled":True,
                  "pools":[{"pool":addr,"source_slot":42,"source_sha256":"a"*64,
                            "signed_transaction_hashes":[str(i)*64 for i in range(1,5)],
                            "source_vault_debit_credit_verified":True}]}
        with patch("arb.meteora_dbc_signed_registry_merge.audit",return_value=accepted):
            registry,report=merge({"pools":[]},source,{},{},{},required=1)
        self.assertEqual(len(registry["pools"]),1)
        entry=registry["pools"][0]
        self.assertFalse(entry["usable_for_arbitrage"])
        self.assertTrue(entry["requires_live_state_revalidation"])
        self.assertTrue(entry["signed_provenance"]["vault_debit_credit_verified"])
        self.assertFalse(report["registry_admission_approved"])
        self.assertFalse(report["usable_for_arbitrage"])
        previous={**entry,"usable_for_arbitrage":True,
                  "requires_live_state_revalidation":False}
        with patch("arb.meteora_dbc_signed_registry_merge.audit",return_value=accepted):
            updated,_=merge({"pools":[previous]},source,{},{},{},required=1)
        self.assertFalse(updated["pools"][0]["usable_for_arbitrage"])
        self.assertTrue(updated["pools"][0]["requires_live_state_revalidation"])
        accepted["pools"][0]["source_vault_debit_credit_verified"]=False
        with patch("arb.meteora_dbc_signed_registry_merge.audit",return_value=accepted):
            with self.assertRaisesRegex(ValueError,"vault-backed"):
                merge({"pools":[]},source,{},{},{},required=1)

    def test_require_six_signed_pool_count_bound(self):
        with self.assertRaisesRegex(ValueError,"1-6"):
            merge({"pools":[]},{},{},{},{},required=7)


if __name__=="__main__":unittest.main()
