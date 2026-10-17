import base64
import unittest
from unittest.mock import patch
from arb.orca_whirlpool import PROGRAM, DISCRIMINATOR, SIZE, b58
from arb.token_vaults import TOKEN_PROGRAM
from arb.whirlpool_snapshot import snapshot

def pool_bytes():
    raw=bytearray(SIZE)
    raw[:8]=DISCRIMINATOR
    raw[41:43]=(64).to_bytes(2,"little")
    raw[49:65]=(100).to_bytes(16,"little")
    raw[65:81]=(1<<64).to_bytes(16,"little")
    raw[101:133]=bytes([1])*32
    raw[133:165]=bytes([3])*32
    raw[181:213]=bytes([2])*32
    raw[213:245]=bytes([4])*32
    return bytes(raw)

def vault_bytes(mint):
    raw=bytearray(165)
    raw[:32]=bytes([mint])*32
    raw[32:64]=bytes([7])*32
    raw[64:72]=(1000).to_bytes(8,"little")
    raw[108]=1
    return bytes(raw)

def account(owner, raw):
    return {"owner":owner,"executable":False,"data":[base64.b64encode(raw).decode(),"base64"]}

class SnapshotTests(unittest.TestCase):
    @patch("arb.whirlpool_snapshot.call")
    @patch("arb.whirlpool_snapshot.fetch_pool")
    def test_same_slot_and_vault_mints(self, fetch_pool, call):
        fetch_pool.return_value={"token_vault_a":b58(bytes([3])*32),
                                 "token_vault_b":b58(bytes([4])*32)}
        call.return_value={"context":{"slot":12345},"value":[
            account(PROGRAM,pool_bytes()),
            account(TOKEN_PROGRAM,vault_bytes(1)),
            account(TOKEN_PROGRAM,vault_bytes(2))]}
        state=snapshot("http://localhost", "pool")
        self.assertEqual(state["slot"],12345)
        self.assertEqual(state["vault_a"]["amount_base_units"],1000)
        self.assertEqual(call.call_args.args[1],"getMultipleAccounts")

    @patch("arb.whirlpool_snapshot.call")
    @patch("arb.whirlpool_snapshot.fetch_pool")
    def test_wrong_vault_owner_fails(self, fetch_pool, call):
        fetch_pool.return_value={"token_vault_a":b58(bytes([3])*32),
                                 "token_vault_b":b58(bytes([4])*32)}
        call.return_value={"context":{"slot":123},"value":[
            account(PROGRAM,pool_bytes()),account("spoof",vault_bytes(1)),
            account(TOKEN_PROGRAM,vault_bytes(2))]}
        with self.assertRaises(ValueError):
            snapshot("rpc","pool")

    @patch("arb.whirlpool_snapshot.call")
    @patch("arb.whirlpool_snapshot.fetch_pool")
    def test_snapshot_slot_required(self, fetch_pool, call):
        fetch_pool.return_value={"token_vault_a":b58(bytes([3])*32),
                                 "token_vault_b":b58(bytes([4])*32)}
        call.return_value={"value":[]}
        with self.assertRaises(ValueError):
            snapshot("rpc","pool")
