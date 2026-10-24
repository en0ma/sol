import base64
import unittest
from unittest.mock import patch
from arb.orca_whirlpool import b58
from arb.token_vaults import decode_token_account, fetch_vaults, verify_whirlpool_vaults, TOKEN_PROGRAM

def vault(mint_byte, authority_byte, amount):
    b=bytearray(165)
    b[:32]=bytes([mint_byte])*32
    b[32:64]=bytes([authority_byte])*32
    b[64:72]=amount.to_bytes(8,"little")
    b[108]=1
    return bytes(b)

class VaultTests(unittest.TestCase):
    def test_decode(self):
        d=decode_token_account(vault(1,9,1234))
        self.assertEqual(d["mint"], b58(bytes([1])*32))
        self.assertEqual(d["amount_base_units"],1234)

    def test_uninitialized_rejected(self):
        with self.assertRaises(ValueError): decode_token_account(bytes(165))

    @patch("arb.token_vaults.call")
    def test_fetch_rejects_spoofed_owner(self, call):
        call.return_value={"value":[{"owner":"spoof","executable":False,
            "data":[base64.b64encode(vault(1,9,10)).decode(),"base64"]}]}
        with self.assertRaises(ValueError): fetch_vaults("http://localhost",["a"])

    @patch("arb.token_vaults.fetch_vaults")
    def test_vault_mints_and_authority(self, fetch):
        mint_a=b58(bytes([1])*32)
        mint_b=b58(bytes([2])*32)
        pool={"token_vault_a":"a","token_vault_b":"b","token_mint_a":mint_a,"token_mint_b":mint_b}
        fetch.return_value={"a":{"mint":mint_a,"authority":"same","amount_base_units":100},
                            "b":{"mint":mint_b,"authority":"same","amount_base_units":200}}
        self.assertEqual(verify_whirlpool_vaults("rpc",pool)["vault_a"]["amount_base_units"],100)
        fetch.return_value["b"]["authority"]="different"
        with self.assertRaises(ValueError): verify_whirlpool_vaults("rpc",pool)

    def test_duplicate_vault_rejected(self):
        with self.assertRaises(ValueError): fetch_vaults("rpc",["same","same"])
