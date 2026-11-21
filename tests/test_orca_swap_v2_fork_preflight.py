import unittest
from arb.orca_swap_v2_fork_preflight import preflight_same_fork

class SameForkPreflightTests(unittest.TestCase):
    def evidence(self):
        quote={"fork_id":"surfpool-instance-A","slot":42,
               "amounts_reconciled_against_fork_state":True}
        pool={"fork_id":"surfpool-instance-A","slot":42,
              "pool_accounts_verified_same_fork":True}
        user={"fork_id":"surfpool-instance-A","slot":42,
              "owner_signature_control_verified":True,
              "user_token_accounts_verified":True}
        return quote,pool,user

    def test_matching_evidence_never_authorizes_trade(self):
        result=preflight_same_fork(*self.evidence())
        self.assertTrue(result["preflight_evidence_complete"])
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])

    def test_fork_or_slot_mismatch_fails(self):
        for section,key,value,reason in (
            (0,"fork_id","mainnet","FORK_PROVENANCE_MISMATCH"),
            (1,"slot",43,"SNAPSHOT_SLOTS_MISMATCH"),
            (2,"slot",None,"UNVERIFIED_SLOTS"),
            (2,"user_token_accounts_verified",False,"USER_TOKEN_ACCOUNTS_NOT_VERIFIED"),
            (0,"amounts_reconciled_against_fork_state",False,"QUOTE_NOT_RECONCILED")):
            with self.subTest(section=section,key=key):
                inputs=list(self.evidence())
                inputs[section][key]=value
                result=preflight_same_fork(*inputs)
                self.assertIn(reason,result["failure_reasons"])
                self.assertFalse(result["preflight_evidence_complete"])

if __name__=="__main__":
    unittest.main()
