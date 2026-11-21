"""DBC independent signed acceptance is impossible without real source receipts."""
import unittest,hashlib,base64
from solders.pubkey import Pubkey
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.meteora_dbc_signed_audit import audit,verify_vault_deltas,AUTHORITY,TOKEN_PROGRAM


class DbcIndependentSignedBoundaryTests(unittest.TestCase):
    def test_empty_untrusted_receipts_do_not_verify(self):
        source={"status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"}
        sdk={"status":"DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY"}
        native={"status":"INDEPENDENT_DBC_ORIGINAL_NATIVE_FEE_CURVE_SDK_PARITY",
                "verified_pools":1,"verified_trials":4}
        signed={"status":"DBC_SIGNED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTED",
                "independent_signed_audit_accepted":False,"actionable":False,
                "broadcast":False,"pools":[]}
        with self.assertRaisesRegex(ValueError,"four-signature-per-pool"):
            audit(source,sdk,native,signed,required=1)

    def test_no_signed_status_substitution(self):
        with self.assertRaisesRegex(ValueError,"prerequisite absent"):
            audit({}, {}, {}, {"status":"CI_SUCCESS"},required=1)


    def test_vault_conservation_both_directions_and_tamper(self):
        base=str(Pubkey.new_unique())
        quote=str(Pubkey.new_unique())
        fields={"base_vault":"base-vault","quote_vault":"quote-vault",
                "base_mint":base,"quote_mint":quote}
        def encoded(mint,owner,amount):
            return base64.b64encode(token_account_bytes(mint,owner,amount)).decode()
        saved_base=token_account_bytes(base,AUTHORITY,1000)
        saved_quote=token_account_bytes(quote,AUTHORITY,2000)
        accounts={
            "base-vault":{"owner":TOKEN_PROGRAM,
                          "account_base64":base64.b64encode(saved_base).decode(),
                          "sha256":hashlib.sha256(saved_base).hexdigest()},
            "quote-vault":{"owner":TOKEN_PROGRAM,
                           "account_base64":base64.b64encode(saved_quote).decode(),
                           "sha256":hashlib.sha256(saved_quote).hexdigest()}}
        forward=[encoded(base,AUTHORITY,1010),encoded(quote,AUTHORITY,1993)]
        reverse=[encoded(base,AUTHORITY,993),encoded(quote,AUTHORITY,2010)]
        self.assertEqual(
            verify_vault_deltas(fields,accounts,forward,"base_to_quote",10,7),
            {"before":[1000,2000],"after":[1010,1993]})
        self.assertEqual(
            verify_vault_deltas(fields,accounts,reverse,"quote_to_base",10,7),
            {"before":[1000,2000],"after":[993,2010]})
        with self.assertRaisesRegex(ValueError,"input credit"):
            verify_vault_deltas(fields,accounts,
                [encoded(base,AUTHORITY,1009),forward[1]],"base_to_quote",10,7)
        with self.assertRaisesRegex(ValueError,"output debit"):
            verify_vault_deltas(fields,accounts,
                [forward[0],encoded(quote,AUTHORITY,1994)],
                "base_to_quote",10,7)
        with self.assertRaisesRegex(ValueError,"authority"):
            verify_vault_deltas(fields,accounts,
                [encoded(base,str(Pubkey.new_unique()),1010),forward[1]],
                "base_to_quote",10,7)
        with self.assertRaisesRegex(ValueError,"poststates"):
            verify_vault_deltas(fields,accounts,None,"base_to_quote",10,7)
        accounts["base-vault"]["sha256"]="0"*64
        with self.assertRaisesRegex(ValueError,"digest changed"):
            verify_vault_deltas(fields,accounts,forward,"base_to_quote",10,7)

    def test_non_six_required_count_rejected(self):
        with self.assertRaisesRegex(ValueError,"prerequisite absent"):
            audit({}, {}, {}, {},required=7)


if __name__=="__main__":unittest.main()
