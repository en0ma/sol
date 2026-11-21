import sys
import types
import unittest
from unittest.mock import patch
from arb.pumpswap_canonical import classify_pool, PUMP_PROGRAM


class FakePubkey:
    def __init__(self,value): self.value=value
    @classmethod
    def from_string(cls,value): return cls(value)
    @classmethod
    def find_program_address(cls,seeds,program):
        assert seeds[0]==b"pool-authority"
        assert program.value==PUMP_PROGRAM
        assert seeds[1]==b"BASE"
        return cls("CANONICAL"),254
    def __bytes__(self): return self.value.encode()
    def __str__(self): return self.value
    def __eq__(self,other): return isinstance(other,FakePubkey) and self.value==other.value


class PumpSwapCanonicalTests(unittest.TestCase):
    def test_creator_pda_not_coin_creator_controls_canonical(self):
        module=types.ModuleType("solders.pubkey")
        module.Pubkey=FakePubkey
        with patch.dict(sys.modules,{"solders":types.ModuleType("solders"),
                                     "solders.pubkey":module}):
            state={"base_mint":"BASE","creator":"CANONICAL",
                   "coin_creator":"unrelated"}
            self.assertTrue(classify_pool(state)["canonical"])
            state["creator"]="noncanonical"
            state["coin_creator"]="CANONICAL"
            self.assertFalse(classify_pool(state)["canonical"])
            self.assertTrue(classify_pool(state)["canonical_pool_verified"])
