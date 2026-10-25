import unittest
from unittest.mock import patch,MagicMock
from arb.atomic_graph_coordinator import signed_prefix_observer
class FakeSigner:
    def pubkey(self):return "payer"
class FakeTxn:
    def verify(self):pass
    def __bytes__(self):return b"x"*200
class FakeFactory:
    @staticmethod
    def new_signed_with_payer(*args):return FakeTxn()
class Tests(unittest.TestCase):
    def legs(self):
        return [{"venue":"orca","pool":"one","input_mint":"A","output_mint":"B"},
                {"venue":"raydium_cpmm","pool":"two","input_mint":"B","output_mint":"C"},
                {"venue":"pumpswap","pool":"three","input_mint":"C","output_mint":"A"}]
    def test_prefix_observes_each_signed_cumulative_output(self):
        legs=self.legs()
        balances=[100,0,0,0]
        signed_outputs=[40,25]
        def simulate(rpc,tx,keys):
            slot=call_count[0];call_count[0]+=1
            rows=[None]*4
            for index in range(slot+2):
                rows[index]={"owner":"token","data":["YQ==","base64"]}
            return {"err":None,"accounts":rows},200
        call_count=[0]
        decode_index=[0]
        def decode(raw):
            slot=call_count[0]-1
            index=decode_index[0]
            decode_index[0]+=1
            # Decode call count accumulates across separate signed prefix
            # simulations; each next RPC result restarts its account indices.
            index=index % (slot+2)
            return {"mint":["A","B","C"][index],"authority":"owner",
                    "amount_base_units":(0 if index<=slot else signed_outputs[slot])}
        with patch("arb.damm_cpmm_atomic_offline._post",return_value=balances),patch(
             "arb.atomic_graph_coordinator.build_leg",return_value="ix") as builder,patch(
             "arb.rpc.call",return_value={"value":{"blockhash":"fake"}}),patch(
             "solders.hash.Hash.from_string",return_value=MagicMock()),patch(
             "solders.transaction.Transaction",FakeFactory),patch(
             "arb.damm_cpmm_atomic_offline._simulate",side_effect=simulate),patch(
             "arb.token_vaults.decode_token_account",side_effect=decode),patch(
             "arb.token_vaults.TOKEN_PROGRAM","token"):
            observer=signed_prefix_observer("http://127.0.0.1:8899",legs,
                ["A","B","C","A"],{("orca","one"):{},("raydium_cpmm","two"):{}},
                {("orca","one"):{},("raydium_cpmm","two"):{}},
                "owner",["a","b","c","d"],FakeSigner(),initial_amount=100)
            out1=observer(0,legs[0],100)
            out2=observer(1,legs[1],out1["output_base_units"])
        self.assertEqual([out1["output_base_units"],out2["output_base_units"]],[40,25])
        self.assertEqual(builder.call_count,2)
        self.assertEqual(builder.call_args_list[1].args[-2],40)
    def test_repeated_index_rejected(self):
        legs=self.legs()
        with patch("arb.damm_cpmm_atomic_offline._post",return_value=[100,0,0,0]):
            observer=signed_prefix_observer("http://127.0.0.1:8899",legs,
                ["A","B","C","A"],{},{},"owner",["a","b","c","d"],FakeSigner(),initial_amount=100)
        with self.assertRaises(ValueError):observer(1,legs[1],90)
if __name__=="__main__":unittest.main()
