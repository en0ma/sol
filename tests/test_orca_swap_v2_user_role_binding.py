import unittest
from arb.orca_swap_v2_user_role_binding import bind_local_user_accounts
from arb.orca_swap_v2_metas import ACCOUNT_ROLES

def fixture():
    roles={role:"address-"+role for role in ACCOUNT_ROLES}
    roles.update(token_authority="test-signer",token_program_a="token-program",
                 token_program_b="token-program",token_mint_a="mint-a",
                 token_mint_b="mint-b",token_owner_account_a="account-a",
                 token_owner_account_b="account-b")
    metas=[{"role":role,"address":roles[role],"is_signer":role=="token_authority"}
           for role in ACCOUNT_ROLES]
    a={"account":"account-a","authority":"test-signer","slot":42,
       "local_rpc_verified":True,"token_program":"token-program","mint":"mint-a"}
    b={"account":"account-b","authority":"test-signer","slot":42,
       "local_rpc_verified":True,"token_program":"token-program","mint":"mint-b"}
    return metas,a,b

class UserRoleBindingTests(unittest.TestCase):
    def test_matching_roles_remain_diagnostic_only(self):
        metas,a,b=fixture()
        result=bind_local_user_accounts(metas,a,b,"test-signer")
        self.assertTrue(result["local_user_accounts_match_swap_v2_roles"])
        self.assertFalse(result["pool_and_quote_same_fork_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["signed_simulation_verified"])

    def test_wrong_owner_slot_or_program_rejected(self):
        for target,key,value in ((1,"authority","other"),(2,"slot",43),
                                 (1,"token_program","another-program"),
                                 (2,"account","other-account"),
                                 (1,"local_rpc_verified",False)):
            with self.subTest(target=target,key=key):
                metas,a,b=fixture()
                [metas,a,b][target][key]=value
                with self.assertRaises(ValueError):
                    bind_local_user_accounts(metas,a,b,"test-signer")

if __name__=="__main__":
    unittest.main()
