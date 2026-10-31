import unittest
from unittest.mock import patch
from arb.orca_cycle_assembler import assemble_orca_cycle
from arb.orca_whirlpool import SOL

A="3NZ9JMVBmGAqocybic2c7LQCJScmgsAZ6vQqTDzcqmJh"
B="cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij"
POOLS=["B5EwJVDuAauzUEEdwvbuXzbFFgEYnUqqS37TUM1c4PQA",
       "4v8ufj8Hj7UvFgtofQJAtzUud5xomwZfEqfCTHZ4wM72",
       "CeaZcxBNLpJWtxzt58qQmfMBtJY8pQLvursXTJYGQpbN"]
TOKENS=[SOL,A,B,SOL]
ROUTE={"tokens":TOKENS,"legs":[
    {"venue":"orca","pool":p,"from":TOKENS[i],"to":TOKENS[i+1]}
    for i,p in enumerate(POOLS)]}
STATES={
    POOLS[0]:{"token_mint_a":SOL,"token_mint_b":A},
    POOLS[1]:{"token_mint_a":B,"token_mint_b":A},
    POOLS[2]:{"token_mint_a":SOL,"token_mint_b":B}}
ORACLES={p:"oracle"+str(i) for i,p in enumerate(POOLS)}
ACCOUNTS={t:"account"+str(i) for i,t in enumerate(TOKENS[:-1])}

class OrcaCycleAssemblyTests(unittest.TestCase):
    @patch("arb.orca_cycle_assembler.build_swap")
    def test_three_hops_preserve_order_direction_accounts(self, build):
        build.side_effect=["ix1","ix2","ix3"]
        result=assemble_orca_cycle(ROUTE,STATES,ORACLES,ACCOUNTS,"authority",
                                   [100,90,80],[1,1,1])
        self.assertEqual(result,["ix1","ix2","ix3"])
        self.assertEqual([c.kwargs["a_to_b"] for c in build.call_args_list],
                         [True,False,False])
        self.assertEqual([c.args[0] for c in build.call_args_list],POOLS)
        self.assertEqual([c.args[3] for c in build.call_args_list],
                         [ACCOUNTS[SOL],ACCOUNTS[B],ACCOUNTS[SOL]])

    def test_cross_asset_exit_rejected(self):
        bad=dict(ROUTE,tokens=[SOL,A,B,A])
        with self.assertRaisesRegex(ValueError,"close"):
            assemble_orca_cycle(bad,STATES,ORACLES,ACCOUNTS,"authority",
                                [100,90,80],[1,1,1])

    def test_missing_intermediate_account_rejected(self):
        with self.assertRaisesRegex(ValueError,"missing user account"):
            assemble_orca_cycle(ROUTE,STATES,ORACLES,{SOL:"only"},"authority",
                                [100,90,80],[1,1,1])
