"""Synthetic packets test archive parsing and source gate; not real acceptance."""
import base64
import json
import unittest
from unittest.mock import patch
from solders.hash import Hash
from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.message import Message, MessageV0
from solders.address_lookup_table_account import AddressLookupTableAccount
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from arb import blockzilla_discovery as b


def key():
    return str(Pubkey.new_unique())


def tx_row(versioned=False, cpi=False):
    payer, pool = Keypair(), Pubkey.new_unique()
    program = Pubkey.from_string(b.VENUES["orca"][0])
    outer = Pubkey.new_unique() if cpi else program
    accounts = [AccountMeta(pool, False, True)]
    if cpi:
        accounts.append(AccountMeta(program, False, False))
    ix = Instruction(outer, b"x", accounts)
    if versioned:
        table = AddressLookupTableAccount(Pubkey.new_unique(), [pool])
        msg = MessageV0.try_compile(payer.pubkey(), [ix], [table], Hash.default())
        loaded = {"writable": [str(pool)], "readonly": []}
    else:
        msg = Message.new_with_blockhash([ix], payer.pubkey(), Hash.default())
        loaded = {"writable": [], "readonly": []}
    packet = VersionedTransaction(msg, [payer])
    keys = [str(x) for x in msg.account_keys] + loaded["writable"]
    children = [{"index": 0, "instructions": [{"programIdIndex": keys.index(str(program)),
                 "accounts": [keys.index(str(pool))], "data": "1"}]}] if cpi else []
    return {"transaction": [base64.b64encode(bytes(packet)).decode(), "base64"],
            "meta": {"err": None, "loadedAddresses": loaded, "innerInstructions": children}}, str(pool)


class BlockzillaTests(unittest.TestCase):
    def test_direct_and_cpi_legacy_and_v0(self):
        for versioned in (False, True):
            for cpi in (False, True):
                with self.subTest(versioned=versioned, cpi=cpi):
                    row, pool = tx_row(versioned, cpi)
                    self.assertEqual(b.decode_transaction(row)["hints"], {("orca", pool)})

    def test_failed_unknown_and_unresolved_lookup(self):
        row, _ = tx_row(True)
        row["meta"]["err"] = {"InstructionError": [0, "Custom"]}
        self.assertIsNone(b.decode_transaction(row))
        del row["meta"]["err"]
        with self.assertRaises(ValueError):
            b.decode_transaction(row)
        row["meta"]["err"] = None
        row["meta"]["loadedAddresses"] = None
        with self.assertRaises(ValueError):
            b.decode_transaction(row)

    def test_crosscheck_mismatch_never_emits_hints(self):
        row, pool = tx_row()
        block = {"blockhash": key(), "parentSlot": 99, "transactions": [row]}
        raw = json.dumps({"result": block}).encode()

        def rpc(_url, method, _params, **_kwargs):
            if method == "getBlock":
                return {"blockhash": block["blockhash"], "parentSlot": 99}
            if method == "getTransaction":
                return {**row, "slot": 100}
            raise AssertionError(method)

        report = b.scan("https://independent.invalid", [], start_slot=100, blocks=1,
                        fetcher=lambda *_: raw, rpc_call=rpc)
        self.assertEqual(report["crosschecked_blocks"], 1)
        self.assertEqual(report["candidate_hints"][0]["address"], pool)
        self.assertEqual(report["independent_rpc_logical_requests"],
                         {"getBlock": 1, "getTransaction": 1})
        self.assertFalse(report["broadcast"])
        bad = b.scan("https://independent.invalid", [], start_slot=100, blocks=1,
                     fetcher=lambda *_: raw,
                     rpc_call=lambda u, m, p, **kw: rpc(u, m, p, **kw) if m == "getBlock"
                     else {**row, "slot": 101})
        self.assertEqual(bad["crosschecked_blocks"], 0)
        self.assertEqual(bad["candidate_hints"], [])

    def test_source_verifier_and_immutable_baseline(self):
        a, c, d, pool, p1, p2 = (key() for _ in range(6))
        baseline = [{"venue": "orca", "address": p1, "mints": [a, c]},
                    {"venue": "orca", "address": p2, "mints": [c, d]}]
        old = json.dumps(baseline)
        hints = {"schema": 1, "status": "HISTORICAL_HINTS_ONLY", "crosschecked_blocks": 1,
                 "candidate_hints": [{"venue": "orca", "address": pool,
                    "first_observation": {"slot": 100, "signature": "fixture"}}], **b.SAFE}
        program, size, x, y, _ = b.VENUES["orca"]
        account = {"owner": program, "executable": False,
                   "data": [base64.b64encode(bytes(size)).decode(), "base64"]}

        def rpc(*_args):
            return {"context": {"slot": 123}, "value": [account]}

        def verified(_rpc, venue, addr, state):
            self.assertEqual(state, "decoded")
            return {"venue": venue, "address": addr, "mints": [a, d], "slot": 124}

        with patch.dict(b.VENUES, {"orca": (program, size, x, y, lambda _: "decoded")}):
            report = b.authenticate("http://127.0.0.1:8899", baseline, hints,
                                    rpc_call=rpc, verify_pool=verified)
            self.assertEqual(report["new_source_verified_pool_count"], 1)
            self.assertEqual(set(report["additional_topology_start_mints"]), {a, c, d})
            self.assertFalse(report["admitted_to_primary_registry"])
            self.assertFalse(report["signed_simulation_verified"])
            self.assertEqual(json.dumps(baseline), old)
            account["owner"] = key()
            rejected = b.authenticate("http://127.0.0.1:8899", baseline, hints,
                                      rpc_call=rpc, verify_pool=lambda *_: self.fail("wrong owner"))
            self.assertEqual(rejected["new_source_verified_pool_count"], 0)
        with self.assertRaises(ValueError):
            b.authenticate("https://remote.invalid", baseline, hints)
        with self.assertRaises(ValueError):
            b.authenticate("http://127.0.0.1:8899", baseline,
                           {**hints, "crosschecked_blocks": 0})


if __name__ == "__main__":
    unittest.main()
