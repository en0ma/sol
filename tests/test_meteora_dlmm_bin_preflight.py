import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dlmm_bin_preflight import active_bin_array_index,bin_array_pda,check_active_bin_array
from arb.meteora_dlmm import PROGRAM

class DlmmBinPreflightTests(unittest.TestCase):
    def test_signed_floor_not_truncation(self):
        for bin_id,expected in [(-141,-3),(-71,-2),(-70,-1),(-1,-1),(0,0),(69,0),(70,1)]:
            with self.subTest(bin_id=bin_id):
                self.assertEqual(active_bin_array_index(bin_id),expected)

    def test_distinct_signed_pdas(self):
        pool=str(Pubkey.new_unique())
        self.assertNotEqual(bin_array_pda(pool,-1),bin_array_pda(pool,0))
        self.assertNotEqual(bin_array_pda(pool,0),bin_array_pda(pool,1))

    def test_disallows_remote_validator(self):
        with patch("arb.meteora_dlmm_bin_preflight.call") as rpc:
            with self.assertRaises(ValueError):
                check_active_bin_array("https://api.mainnet-beta.solana.com",
                                       str(Pubkey.new_unique()))
            rpc.assert_not_called()


class BitmapExtensionSourceTests(unittest.TestCase):
    def test_bitmap_extension_authentication_and_manifest_membership(self):
        import base64
        from solders.pubkey import Pubkey
        from arb.meteora_dlmm_bin_preflight import (bitmap_extension_pda,
            contextual_bitmap_extension,verified_bitmap_extension_address,
            BITMAP_EXTENSION_DISC,BITMAP_EXTENSION_SIZE)
        from arb.meteora_dlmm import PROGRAM
        pool=str(Pubkey.new_unique())
        address=bitmap_extension_pda(pool)
        raw=bytearray(BITMAP_EXTENSION_SIZE)
        raw[:8]=BITMAP_EXTENSION_DISC
        raw[8:40]=bytes(Pubkey.from_string(pool))
        raw[40]=5;raw[808]=128
        record={"owner":PROGRAM,"executable":False,
                "data":[base64.b64encode(raw).decode(),"base64"]}
        accounts={address:record}
        claim=contextual_bitmap_extension(pool,accounts)
        self.assertEqual(claim["positive_initialized_array_count"],2)
        self.assertEqual(claim["negative_initialized_array_count"],1)
        proof={"bitmap_extension_source":claim}
        fixture={"accounts":accounts,"state_account_addresses":[address]}
        self.assertEqual(verified_bitmap_extension_address(pool,proof,fixture),address)
        with self.assertRaisesRegex(ValueError,"outside"):
            verified_bitmap_extension_address(pool,proof,{**fixture,"state_account_addresses":[]})
        with self.assertRaisesRegex(ValueError,"differs"):
            verified_bitmap_extension_address(pool,proof,{"accounts":{},"state_account_addresses":[]})
        absent=contextual_bitmap_extension(pool,{})
        self.assertIsNone(verified_bitmap_extension_address(pool,
            {"bitmap_extension_source":absent},{"accounts":{},"state_account_addresses":[]}))
        with self.assertRaises(ValueError):
            contextual_bitmap_extension(pool,{address:{**record,"owner":"wrong"}})
        raw[8:40]=bytes(Pubkey.new_unique())
        with self.assertRaisesRegex(ValueError,"parent"):
            contextual_bitmap_extension(pool,{address:{**record,
                "data":[base64.b64encode(raw).decode(),"base64"]}})
