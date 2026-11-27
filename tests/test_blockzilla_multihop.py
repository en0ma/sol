import unittest
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.instruction import Instruction
from solders.transaction import Transaction
import base64
from arb.blockzilla_multihop import candidate_routes,decode_packet,digest
from arb.opportunity_graph import cycles

def key():return str(Pubkey.new_unique())

class MultihopTests(unittest.TestCase):
    def test_hint_graph_requires_explicit_mode_and_novel_pool(self):
        mints=[key() for _ in range(4)]
        rows=[{"venue":v,"address":key(),"mints":[mints[i],mints[(i+1)%4]]}
              for i,v in enumerate(("raydium_cpmm","meteora_dlmm","orca","raydium_clmm"))]
        self.assertEqual(cycles(rows,max_hops=4,min_hops=4),[])
        picked,_=candidate_routes(rows[1:],[{**rows[0],"source_verified_only":True}])
        self.assertTrue(picked[4])
        self.assertFalse(picked[5])
        for row in picked[4]:
            self.assertEqual(row["status"],"HINT_ONLY_UNQUOTED")
            self.assertEqual(row["novel_pool_identities"],[["raydium_cpmm",rows[0]["address"]]])
            self.assertFalse(row["broadcast"])
    def test_legacy_packet_crypto_and_digest(self):
        payer=Keypair()
        tx=Transaction.new_signed_with_payer([Instruction(Pubkey.new_unique(),b"x",[])],
                 payer.pubkey(),[payer],Hash.new_unique())
        raw=bytes(tx);wire=base64.b64encode(raw).decode()
        decoded,lookup,_=decode_packet(wire,digest(raw),str(tx.signatures[0]),None)
        self.assertEqual(bytes(decoded),raw)
        self.assertIsNone(lookup)
        with self.assertRaises(ValueError):
            decode_packet(wire,"bad",str(tx.signatures[0]),None)

if __name__=="__main__":unittest.main()
