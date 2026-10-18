import unittest
from solders.pubkey import Pubkey
from arb.orca_whirlpool import PROGRAM
from arb.orca_swap_v2_metas import ACCOUNT_ROLES,WRITABLE,SIGNERS,MEMO_PROGRAM
from arb.orca_swap_v2_candidate import unsigned_swap_v2_candidate

def fixture():
    return [{"role":role,
             "address":MEMO_PROGRAM if i==2 else str(Pubkey.new_unique()),
             "is_writable":i in WRITABLE,"is_signer":i in SIGNERS}
            for i,role in enumerate(ACCOUNT_ROLES)]

class UnsignedSwapV2CandidateTests(unittest.TestCase):
    def test_instruction_assembly_remains_unverified(self):
        metas=fixture()
        result=unsigned_swap_v2_candidate(metas,100,90,2**64,True,True)
        instruction=result["instruction"]
        self.assertEqual(str(instruction.program_id),PROGRAM)
        self.assertEqual(len(instruction.accounts),15)
        self.assertEqual(bytes(instruction.data)[40:],bytes((1,1,0)))
        self.assertTrue(instruction.accounts[3].is_signer)
        self.assertTrue(instruction.accounts[11].is_writable)
        self.assertFalse(result["signed_simulation_verified"])
        self.assertFalse(result["actionable"])
        self.assertFalse(result["broadcast"])

    def test_invalid_key_and_bad_layout_fail_closed(self):
        metas=fixture()
        metas[0]["address"]="not-a-pubkey"
        with self.assertRaises(ValueError):
            unsigned_swap_v2_candidate(metas,1,0,2**64,True,True)
        metas=fixture()
        metas[3]["is_signer"]=False
        with self.assertRaises(ValueError):
            unsigned_swap_v2_candidate(metas,1,0,2**64,True,True)

if __name__=="__main__":
    unittest.main()
