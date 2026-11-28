import unittest
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.instruction import Instruction
from solders.transaction import Transaction
import base64
from arb.blockzilla_multihop import candidate_routes,decode_packet,digest,seed_window
from arb.opportunity_graph import cycles

def key():return str(Pubkey.new_unique())

class MultihopTests(unittest.TestCase):
    def test_hint_graph_requires_explicit_mode_and_novel_pool(self):
        mints=[key() for _ in range(4)]
        rows=[{"venue":v,"address":key(),"mints":[mints[i],mints[(i+1)%4]]}
              for i,v in enumerate(("raydium_cpmm","meteora_dlmm","orca","raydium_clmm"))]
        with self.assertRaisesRegex(ValueError,"empty anchors"):
            cycles(rows,max_hops=4,min_hops=4)
        self.assertEqual(cycles(rows,anchors=[mints[0]],max_hops=4,min_hops=4),[])
        picked,_=candidate_routes(rows[1:],[{**rows[0],"source_verified_only":True}])
        self.assertTrue(picked[4])
        self.assertFalse(picked[5])
        for row in picked[4]:
            self.assertEqual(row["status"],"HINT_ONLY_UNQUOTED")
            self.assertEqual(row["novel_pool_identities"],[["raydium_cpmm",rows[0]["address"]]])
            self.assertFalse(row["broadcast"])
    def test_seeded_budget_cannot_be_exhausted_by_other_cycles(self):
        a,b,c,d=[key() for _ in range(4)]
        novel={"venue":"raydium_cpmm","address":key(),"mints":[a,b]}
        alternate={"venue":"orca","address":key(),"mints":[a,b]}
        rows=[alternate,novel,
              {"venue":"meteora_dlmm","address":key(),"mints":[b,c]},
              {"venue":"raydium_clmm","address":key(),"mints":[c,d]},
              {"venue":"raydium_amm_v4","address":key(),"mints":[d,a]}]
        for anchor in (a,b):
            result=cycles(rows,anchors=[anchor],min_hops=4,max_hops=4,
                max_cycles=1,truncate=True,hint_only=True,
                required_first_pool=("raydium_cpmm",novel["address"]))
            self.assertEqual(len(result),1)
            self.assertEqual(result[0]["legs"][0]["pool"],novel["address"])
            self.assertEqual(result[0]["status"],"HINT_ONLY_UNQUOTED")
        with self.assertRaisesRegex(ValueError,"required first pool"):
            cycles(rows,hint_only=True,required_first_pool=("unknown","pool"))
    def test_six_hop_pressure_is_heuristic_not_acceptance(self):
        mints=[key() for _ in range(6)]
        venues=["raydium_cpmm","orca","meteora_damm_v2",
                "orca","raydium_cpmm","raydium_clmm"]
        rows=[{"venue":v,"address":key(),"mints":[mints[i],mints[(i+1)%6]]}
              for i,v in enumerate(venues)]
        alternative={**rows[1],"venue":"pumpswap","address":key()}
        picked,_=candidate_routes(rows[1:]+[alternative],[{**rows[0],"source_verified_only":True}])
        self.assertEqual(len(picked[6]),2)
        self.assertLess(picked[6][0]["heuristic_venue_lock_pressure"],
                        picked[6][1]["heuristic_venue_lock_pressure"])
        self.assertTrue(picked[6][0]["topology_only"])
        self.assertFalse(picked[6][0]["simulation_verified"])
    def test_seed_window_preserves_middle_edges_and_excludes_disconnected(self):
        mints=[key() for _ in range(6)]
        rows=[{"venue":"raydium_cpmm","address":key(),"mints":[mints[i],mints[(i+1)%6]]}
              for i in range(6)]
        unrelated={"venue":"orca","address":key(),"mints":[key(),key()]}
        window,stats=seed_window(rows+[unrelated],rows[0],hops=6)
        self.assertEqual({p["address"] for p in window},{p["address"] for p in rows})
        self.assertEqual(stats["shortest_return_edges"],5)
        self.assertFalse(stats["pool_window_truncated"])
        small,stats=seed_window(rows,rows[0],hops=6,maximum=3)
        self.assertEqual(len(small),3)
        self.assertEqual(small[0],rows[0])
        self.assertTrue(stats["pool_window_truncated"])
        self.assertEqual(seed_window(rows,rows[0],hops=4)[0],[rows[0]])

    def test_graph_edge_budget_is_explicit(self):
        a,b,c,d=[key() for _ in range(4)]
        rows=[{"venue":"orca","address":key(),"mints":[u,v]}
              for u,v in ((a,b),(b,c),(c,d),(d,a))]
        stats={}
        found=cycles(rows,anchors=[a],min_hops=4,max_hops=4,
                     hint_only=True,truncate=True,max_edge_visits=1,search_stats=stats)
        self.assertEqual(found,[])
        self.assertEqual(stats["edge_visits"],1)
        self.assertEqual(stats["stop_reason"],"EDGE_VISIT_LIMIT")
        self.assertFalse(stats["complete"])
        with self.assertRaisesRegex(ValueError,"edge visit budget"):
            cycles(rows,anchors=[a],hint_only=True,max_edge_visits=1)
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
