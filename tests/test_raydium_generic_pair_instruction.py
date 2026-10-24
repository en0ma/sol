import unittest
from unittest.mock import patch
from arb.raydium_swap import instruction, AUTH_SEED
from arb.raydium_cpmm import PROGRAM
from arb.orca_whirlpool import SOL,USDC
from arb.token_vaults import TOKEN_PROGRAM
from solders.pubkey import Pubkey

RAY="4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R"
def state(m0=SOL,m1=RAY):
    _,bump=Pubkey.find_program_address([AUTH_SEED],Pubkey.from_string(PROGRAM))
    return {"auth_bump":bump,"swap_enabled":True,
            "token_0_mint":m0,"token_1_mint":m1,
            "token_0_program":TOKEN_PROGRAM,"token_1_program":TOKEN_PROGRAM,
            "token_0_vault":str(Pubkey.new_unique()),
            "token_1_vault":str(Pubkey.new_unique()),
            "amm_config":str(Pubkey.new_unique()),
            "observation":str(Pubkey.new_unique())}

def build(s, direction):
    p=[str(Pubkey.new_unique()) for _ in range(4)]
    return instruction(p[0],s,p[1],p[2],p[3],100,1,
                       input_is_token_0=direction,expected_mints=None)

class GenericRaydiumCpmmInstructionTests(unittest.TestCase):
    def test_sol_ray_two_directions(self):
        s=state()
        ix=build(s,True)
        self.assertEqual(str(ix.program_id),PROGRAM)
        self.assertEqual(str(ix.accounts[6].pubkey),s["token_0_vault"])
        self.assertEqual(str(ix.accounts[7].pubkey),s["token_1_vault"])
        ix=build(s,False)
        self.assertEqual(str(ix.accounts[6].pubkey),s["token_1_vault"])
        self.assertEqual(str(ix.accounts[7].pubkey),s["token_0_vault"])

    def test_unverified_pair_not_default_allowed(self):
        with self.assertRaisesRegex(ValueError,"unexpected token pair"):
            instruction(str(Pubkey.new_unique()),state(),str(Pubkey.new_unique()),
                str(Pubkey.new_unique()),str(Pubkey.new_unique()),100,1)

    def test_nonclassic_program_and_disabled_pool_fail(self):
        s=state()
        s["token_1_program"]="TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
        with self.assertRaisesRegex(ValueError,"classic SPL"):
            build(s,True)
        s=state()
        s["swap_enabled"]=False
        with self.assertRaisesRegex(ValueError,"disabled"):
            build(s,True)

    def test_identical_mints_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            build(state(SOL,SOL),True)
