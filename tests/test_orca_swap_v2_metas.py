import unittest
from arb.orca_swap_v2_metas import (
    ACCOUNT_ROLES, WRITABLE, SIGNERS, MEMO_PROGRAM, validate_swap_v2_metas
)

def fixture():
    return [{"role":role,"address":MEMO_PROGRAM if i==2 else f"account-{i}",
             "is_writable":i in WRITABLE,"is_signer":i in SIGNERS}
            for i,role in enumerate(ACCOUNT_ROLES)]

class SwapV2LayoutTests(unittest.TestCase):
    def test_layout_is_diagnostic_only(self):
        result=validate_swap_v2_metas(fixture())
        self.assertTrue(result["layout_matches_reference"])
        self.assertFalse(result["onchain_accounts_verified"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])

    def test_wrong_order_and_flags_rejected(self):
        for field,value in (("role","tick_array_0"),
                            ("is_writable",True),("is_signer",True),
                            ("address","")):
            with self.subTest(field=field):
                accounts=fixture()
                accounts[0][field]=value
                with self.assertRaises(ValueError):
                    validate_swap_v2_metas(accounts)

    def test_duplicated_ticks_and_missing_accounts_rejected(self):
        accounts=fixture()
        accounts[12]["address"]=accounts[11]["address"]
        with self.assertRaisesRegex(ValueError,"duplicate"):
            validate_swap_v2_metas(accounts)
        with self.assertRaisesRegex(ValueError,"15 fixed"):
            validate_swap_v2_metas(fixture()[:-1])

if __name__=="__main__":
    unittest.main()
