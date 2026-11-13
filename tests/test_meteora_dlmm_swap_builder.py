import unittest
from solders.pubkey import Pubkey
from arb.meteora_dlmm_swap import build_swap,SWAP_DISCRIMINATOR
from arb.meteora_dlmm_bin_preflight import bin_array_pda
from arb.meteora_dlmm import PROGRAM

def k():return str(Pubkey.new_unique())
POOL=k()
def state():
    x,y=k(),k()
    return {"status":0,"token_mint_x_program_flag":0,"token_mint_y_program_flag":0,
            "token_x_mint":x,"token_y_mint":y,"reserve_x":k(),"reserve_y":k(),
            "input_mint":x,"output_mint":y,"active_bin_array_index":10}
def assemble(s):
    return build_swap(POOL,s,k(),k(),k(),k(),[bin_array_pda(POOL,10)],1000,1,input_is_x=True)

class DlmmSwapBuilderTests(unittest.TestCase):
    def test_official_idl_account_order_and_discriminator(self):
        s=state(); ix=assemble(s)
        self.assertEqual(str(ix.program_id),PROGRAM)
        self.assertEqual(ix.data[:8],SWAP_DISCRIMINATOR)
        self.assertEqual(len(ix.data),24)
        self.assertEqual(int.from_bytes(ix.data[8:16],"little"),1000)
        self.assertEqual(str(ix.accounts[0].pubkey),POOL)
        self.assertEqual(str(ix.accounts[2].pubkey),s["reserve_x"])
        self.assertEqual(str(ix.accounts[3].pubkey),s["reserve_y"])
        self.assertEqual(str(ix.accounts[6].pubkey),s["token_x_mint"])
        self.assertEqual(str(ix.accounts[7].pubkey),s["token_y_mint"])
        self.assertEqual(str(ix.accounts[1].pubkey),PROGRAM)
        self.assertEqual(str(ix.accounts[9].pubkey),PROGRAM)
        self.assertTrue(ix.accounts[10].is_signer)
        self.assertEqual(str(ix.accounts[-1].pubkey),bin_array_pda(POOL,10))

    def test_reject_mint_direction_and_missing_active_array(self):
        s=state();s["input_mint"]=s["token_y_mint"]
        with self.assertRaisesRegex(ValueError,"direction"):
            assemble(s)
        s=state()
        with self.assertRaisesRegex(ValueError,"active neighborhood"):
            build_swap(POOL,s,k(),k(),k(),k(),[bin_array_pda(POOL,11)],1000,1,input_is_x=True)


    def test_directional_bin_array_traversal_starts_at_active(self):
        s=state()
        bins=[bin_array_pda(POOL,i) for i in (9,10,11)]
        ix=build_swap(POOL,s,k(),k(),k(),k(),bins,1000,1,input_is_x=True)
        self.assertEqual([str(meta.pubkey) for meta in ix.accounts[15:]],
                         [bins[1],bins[0],bins[2]])
        reverse=dict(s,input_mint=s["token_y_mint"],
                     output_mint=s["token_x_mint"])
        ix=build_swap(POOL,reverse,k(),k(),k(),k(),bins,1000,1,
                      input_is_x=False)
        self.assertEqual([str(meta.pubkey) for meta in ix.accounts[15:]],
                         [bins[1],bins[2],bins[0]])

    def test_reject_zero_slippage_floor_and_nonclassic(self):
        s=state()
        with self.assertRaisesRegex(ValueError,"nonzero"):
            build_swap(POOL,s,k(),k(),k(),k(),[bin_array_pda(POOL,10)],1000,0,input_is_x=True)
        s["token_mint_y_program_flag"]=1
        with self.assertRaisesRegex(ValueError,"nonclassic"):
            assemble(s)
