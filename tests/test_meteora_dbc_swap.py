"""DBC original on-chain Anchor account/wire signer role tests."""
import unittest
from solders.pubkey import Pubkey
from arb.meteora_dbc_swap import build_swap, DISC
from arb.meteora_dbc_seventh_venue_source import PROGRAM
from arb.meteora_dbc_seventh_state_capture import TOKEN_PROGRAM


def key(n):
    return str(Pubkey.from_bytes(bytes([n])*32))


def fields():
    return {"config":key(1),"base_mint":key(2),"quote_mint":key(3),
       "base_vault":key(4),"quote_vault":key(5),
       "pool_type":0,"is_migrated":0,"migration_progress":0,
       "base_token_program":TOKEN_PROGRAM,"quote_token_program":TOKEN_PROGRAM}


class OriginalDBCInstructionTests(unittest.TestCase):
    def test_original_idl_exact_in_account_order_and_signer(self):
        ix,proof=build_swap(key(6),fields(),key(7),key(8),key(9),
            10000,100,swap_base_for_quote=True)
        self.assertEqual(str(ix.program_id),PROGRAM)
        self.assertEqual(len(ix.accounts),15)
        self.assertEqual(bytes(ix.data),DISC+(10000).to_bytes(8,"little")+
                         (100).to_bytes(8,"little"))
        self.assertEqual([str(x.pubkey) for x in ix.accounts[1:10]],
            [key(1),key(6),key(8),key(9),key(4),key(5),
             key(2),key(3),key(7)])
        self.assertEqual([i for i,x in enumerate(ix.accounts) if x.is_signer],[9])
        self.assertEqual([i for i,x in enumerate(ix.accounts) if x.is_writable],
                         [2,3,4,5,6,9])
        self.assertFalse(proof["signed_execution_verified"])
        self.assertFalse(proof["registry_admission_approved"])

    def test_token2022_unverified_execution_rejected(self):
        f=fields();f["pool_type"]=1
        with self.assertRaisesRegex(ValueError,"legacy SPL"):
            build_swap(key(6),f,key(7),key(8),key(9),10000,100,
                       swap_base_for_quote=False)

    def test_zero_minimum_rejected(self):
        with self.assertRaisesRegex(ValueError,"nonzero"):
            build_swap(key(6),fields(),key(7),key(8),key(9),10000,0,
                       swap_base_for_quote=True)


if __name__=="__main__":unittest.main()
