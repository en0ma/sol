"""DBC source-state tests: packed layout and fail-closed same-response joins."""
import base64
import hashlib
import unittest
from unittest.mock import patch
from solders.pubkey import Pubkey
from arb.meteora_dbc_seventh_state_capture import (
    parse_pool, capture_pool, PROGRAM, TOKEN_PROGRAM, POOL_AUTHORITY, SYSVAR_OWNER,
)
from arb.meteora_dbc_seventh_venue_source import DISC


def pk(n):
    return str(Pubkey.from_bytes(bytes([n])*32))


def raw_pool():
    r=bytearray(424)
    r[:8]=DISC
    for off,n in ((72,1),(104,2),(136,3),(168,4),(200,5)):
        r[off:off+32]=bytes([n])*32
    r[232:240]=(100).to_bytes(8,"little")
    r[240:248]=(200).to_bytes(8,"little")
    r[296:312]=(1<<64).to_bytes(16,"little")
    return bytes(r)


def account(owner,raw):
    return {"owner":owner,"executable":False,"lamports":1,
            "data":[base64.b64encode(raw).decode(),"base64"]}


def context(pool, mutate=False):
    raw=bytearray(pool)
    if mutate:raw[72:104]=bytes([9])*32
    base_vault=bytearray(165)
    quote_vault=bytearray(165)
    base_vault[:32]=bytes([3])*32
    quote_vault[:32]=bytes([6])*32
    authority=bytes(Pubkey.from_string(POOL_AUTHORITY))
    base_vault[32:64]=authority
    quote_vault[32:64]=authority
    config=bytearray(128)
    config[:8]=hashlib.sha256(b"account:PoolConfig").digest()[:8]
    config[8:40]=bytes([6])*32
    clock=bytearray(40)
    clock[:8]=(101).to_bytes(8,"little")
    clock[32:40]=(1760000000).to_bytes(8,"little",signed=True)
    return {"context":{"slot":102},"value":[
       account(PROGRAM,bytes(raw)),account(PROGRAM,bytes(config)),
       account(TOKEN_PROGRAM,bytes(82)),
       account(TOKEN_PROGRAM,bytes(base_vault)),
       account(TOKEN_PROGRAM,bytes(quote_vault)),
       account(SYSVAR_OWNER,bytes(clock))]}


class DbcStateTests(unittest.TestCase):
    def test_upstream_zero_copy_offsets_and_fee_skip(self):
        f=parse_pool(raw_pool())
        self.assertEqual(f["config"],pk(1))
        self.assertEqual(f["base_mint"],pk(3))
        self.assertEqual(f["quote_vault"],pk(5))
        self.assertEqual(f["base_reserve"],100)
        self.assertEqual(f["quote_reserve"],200)
        self.assertEqual(f["sqrt_price_q64"],1<<64)
        self.assertEqual(f["migration_progress"],0)

    def test_single_contextual_dependency_read(self):
        raw=raw_pool()
        original={"address":pk(8),"account_base64":base64.b64encode(raw).decode(),
          "account_sha256":hashlib.sha256(raw).hexdigest(),"source_slot":100}
        with patch("arb.meteora_dbc_seventh_state_capture.call",return_value=context(raw)) as rpc:
            result=capture_pool("https://readonly.invalid",original)
        self.assertEqual(result["source_slot"],102)
        self.assertEqual(result["clock_slot"],101)
        self.assertFalse(result["pricing_eligible"])
        self.assertFalse(result["signed_parity_verified"])
        self.assertEqual(rpc.call_args.args[1],"getMultipleAccounts")
        self.assertEqual(rpc.call_args.args[2][1]["minContextSlot"],100)

    def test_pool_mutation_rejected(self):
        raw=raw_pool()
        original={"address":pk(8),"account_base64":base64.b64encode(raw).decode(),
          "account_sha256":hashlib.sha256(raw).hexdigest(),"source_slot":100}
        with patch("arb.meteora_dbc_seventh_state_capture.call",return_value=context(raw,True)):
            with self.assertRaisesRegex(ValueError,"identity changed"):
                capture_pool("https://readonly.invalid",original)

    def test_same_roles_allow_new_reserves_without_mixing_snapshots(self):
        raw=raw_pool()
        original={"address":pk(8),"account_base64":base64.b64encode(raw).decode(),
            "account_sha256":hashlib.sha256(raw).hexdigest(),"source_slot":100}
        snapshot=context(raw)
        newer=bytearray(raw)
        newer[232:240]=(101).to_bytes(8,"little")
        snapshot["value"][0]["data"][0]=base64.b64encode(newer).decode()
        with patch("arb.meteora_dbc_seventh_state_capture.call",return_value=snapshot):
            result=capture_pool("https://readonly.invalid",original)
        self.assertEqual(result["pool_fields"]["base_reserve"],101)
        self.assertEqual(result["accounts"][pk(8)]["sha256"],
                         hashlib.sha256(newer).hexdigest())

    def test_wrong_quote_vault_mint_rejected(self):
        raw=raw_pool()
        source={"address":pk(8),"account_base64":base64.b64encode(raw).decode(),
                "account_sha256":hashlib.sha256(raw).hexdigest(),"source_slot":100}
        snapshot=context(raw)
        quote=bytearray(base64.b64decode(snapshot["value"][4]["data"][0]))
        quote[:32]=bytes([99])*32
        snapshot["value"][4]["data"][0]=base64.b64encode(quote).decode()
        with patch("arb.meteora_dbc_seventh_state_capture.call",return_value=snapshot):
            with self.assertRaisesRegex(ValueError,"mint mismatch"):
                capture_pool("https://readonly.invalid",source)

    def test_migrated_rejected(self):
        raw=bytearray(raw_pool());raw[321]=1
        with self.assertRaisesRegex(ValueError,"migrated"):
            parse_pool(bytes(raw))

    def test_bad_digest_rejected_before_rpc(self):
        original={"address":pk(8),"account_base64":base64.b64encode(raw_pool()).decode(),
          "account_sha256":"0"*64,"source_slot":100}
        with patch("arb.meteora_dbc_seventh_state_capture.call") as rpc:
            with self.assertRaisesRegex(ValueError,"digest"):
                capture_pool("https://readonly.invalid",original)
            rpc.assert_not_called()


if __name__=="__main__":
    unittest.main()
