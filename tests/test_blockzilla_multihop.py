import unittest
from solders.pubkey import Pubkey
from solders.keypair import Keypair
from solders.hash import Hash
from solders.instruction import Instruction
from solders.transaction import Transaction
import base64
from arb.blockzilla_multihop import candidate_routes,decode_packet,digest,seed_window,diverse_candidates
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

    def test_venue_priority_search_avoids_lexicographic_budget_bias(self):
        from arb.blockzilla_multihop import VENUE_LOCK_PRESSURE
        a,b,c,d,e=[key() for _ in range(5)]
        seed={"venue":"meteora_dlmm","address":key(),"mints":[a,b]}
        rows=[seed,
            {"venue":"pumpswap","address":key(),"mints":[b,c]},
            {"venue":"raydium_cpmm","address":key(),"mints":[c,a]},
            {"venue":"raydium_cpmm","address":key(),"mints":[b,d]},
            {"venue":"orca","address":key(),"mints":[d,a]}]
        stats={}
        found=cycles(rows,anchors=[a],min_hops=3,max_hops=3,max_cycles=1,
            truncate=True,hint_only=True,required_first_pool=(seed["venue"],seed["address"]),
            venue_priority=VENUE_LOCK_PRESSURE,search_stats=stats)
        self.assertEqual(found[0]["legs"][1]["venue"],"raydium_cpmm")
        self.assertTrue(stats["venue_priority_traversal"])
        self.assertFalse(found[0]["simulation_verified"])
        with self.assertRaisesRegex(ValueError,"venue traversal priorities"):
            cycles(rows,anchors=[a],hint_only=True,venue_priority={"orca":1})
    def test_light_search_retains_novel_seed_and_strict_six_hops(self):
        mints=[key() for _ in range(6)]
        venues=["meteora_dlmm","raydium_cpmm","orca","raydium_cpmm","meteora_damm_v2","raydium_cpmm"]
        rows=[{"venue":v,"address":key(),"mints":[mints[i],mints[(i+1)%6]]}
              for i,v in enumerate(venues)]
        picked,windows=candidate_routes(rows[1:],[{**rows[0],"source_verified_only":True}])
        self.assertEqual(len(picked[6]),1)
        self.assertIn("LIGHT_VENUE_PRIORITY",windows[0]["windows_by_hops"]["6"])
        self.assertEqual(picked[6][0]["hops"],6)
        self.assertTrue(windows[0]["windows_by_hops"]["6"]["LIGHT_VENUE_PRIORITY"]["venue_priority_traversal"])
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
    def test_six_hop_alternatives_avoid_shared_orca_dependencies(self):
        novel=("raydium_cpmm","seed")
        def row(pools):
            legs=[{"venue":v,"pool":p} for v,p in [novel]+pools]
            return {"legs":legs,"venues":sorted({l["venue"] for l in legs})}
        shared=[("orca","missing"),("orca","second")]
        a=row(shared+[("raydium_cpmm","a"),("raydium_cpmm","b"),("raydium_cpmm","c")])
        b=row(shared+[("raydium_cpmm","a"),("raydium_cpmm","b"),("raydium_cpmm","d")])
        c=row([("meteora_dlmm","e"),("raydium_cpmm","f"),("raydium_cpmm","g"),
               ("raydium_clmm","h"),("meteora_damm_v2","i")])
        self.assertEqual(diverse_candidates([a,b,c],{novel},hops=6),[a,c,b])
    def test_four_five_diversity_does_not_repeat_same_bridge(self):
        seed=("raydium_cpmm","novel")
        def row(ids):
            return {"legs":[{"venue":v,"pool":p} for v,p in [seed]+ids],
                    "venues":["raydium_cpmm","orca"]}
        a=row([("orca","a"),("raydium_cpmm","b"),("raydium_cpmm","c")])
        b=row([("orca","a"),("raydium_cpmm","b"),("raydium_cpmm","d")])
        c=row([("orca","x"),("raydium_cpmm","y"),("raydium_cpmm","z")])
        for hops in (4,5):
            self.assertEqual(diverse_candidates([a,b,c],{seed},hops=hops),[a,c,b])
    def test_pump_triangles_both_directions_with_novel_bridge(self):
        from arb.blockzilla_multihop import pump_triangles,WSOL
        token,stable=key(),key()
        pump={"venue":"pumpswap","address":key(),"mints":[token,WSOL]}
        bridge={"venue":"raydium_clmm","address":key(),"mints":[WSOL,stable]}
        seed={"venue":"raydium_cpmm","address":key(),"mints":[token,stable],"source_verified_only":True}
        routes=pump_triangles([pump,bridge],[seed])
        self.assertEqual([r["pump_direction"] for r in routes],["FROM_WSOL","TO_WSOL"])
        for r in routes:
            self.assertEqual(r["legs"][0]["input"],WSOL)
            self.assertEqual(r["legs"][-1]["output"],WSOL)
            self.assertEqual(r["novel_pool_identities"],[["raydium_cpmm",seed["address"]]])
            self.assertFalse(r["simulation_verified"])
        self.assertEqual(routes[0]["legs"][0]["venue"],"pumpswap")
        self.assertEqual(routes[1]["legs"][-1]["venue"],"pumpswap")
        self.assertEqual(pump_triangles([pump,bridge,seed],[]),[])
    def test_economics_ranks_only_same_denomination_and_input(self):
        from arb.blockzilla_multihop import rank_estimated_economics,pricing_summary
        def trial(name,amount,net):
            return {"id":name,"amount":amount,"audit":{
                "status":"N_LEG_PACKET_AND_RECORDED_RESPONSE_RECHECKED",
                "model_matches_terminal":False,"signed_economics":{
                    "start_mint":"SOL","estimated_net_delta_start_mint_base_units":net,
                    "observed_local_fork_gross_delta_start_mint_base_units":net+5000,
                    "estimated_cost_start_mint_base_units":5000,
                    "actionable":False,"broadcast":False,"live_execution_approved":False}}}
        groups=rank_estimated_economics([trial("a",100,-9),trial("b",100,-2),trial("c",200,-1),
                                      {"id":"blocked","amount":100}])
        self.assertEqual(len(groups),2)
        self.assertEqual([r["id"] for r in groups[0]["routes"]],["b","a"])
        self.assertFalse(groups[0]["routes"][0]["net_profit_verified"])
        self.assertEqual(pricing_summary([]),{})
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

    def test_rejected_packet_requires_source_and_runtime_error(self):
        from arb.blockzilla_multihop import audit_account_lock_rejection
        from unittest.mock import patch
        with patch("arb.blockzilla_multihop.fixture_identity"):
            with self.assertRaisesRegex(ValueError,"source or status"):
                audit_account_lock_rejection({"status":"UNVERIFIED"},{"state_account_manifest_sha256":"x"},
                    {"hops":6,"source_slot":1},100000)
    def test_unsigned_footprint_deduplicates_program_and_shared_accounts(self):
        from arb.blockzilla_source_footprint import instruction_footprint
        from solders.instruction import AccountMeta
        payer=Pubkey.new_unique();program=Pubkey.new_unique()
        a,b,c=[Pubkey.new_unique() for _ in range(3)]
        ixs=[Instruction(program,b"x",[AccountMeta(a,False,True),AccountMeta(b,False,True)]),
             Instruction(program,b"y",[AccountMeta(b,False,True),AccountMeta(c,False,True)])]
        self.assertEqual(instruction_footprint(ixs,payer),5)
    def test_footprint_selection_preserves_fallback_and_unknown(self):
        from arb.blockzilla_source_footprint import select_six_hop_sources,SAFE
        def row(rid,n):
            return {"id":rid,"source_account_footprint":{"resolved_account_key_estimate":n,
                "status":"SOURCE_UNSIGNED_INSTRUCTION_KEY_UNION" if n is not None else
                    "SOURCE_FOOTPRINT_RUNTIME_ACCOUNTS_UNAVAILABLE",**SAFE}}
        a,b,c,d=row("a",73),row("b",63),row("c",None),row("d",59)
        self.assertEqual(select_six_hop_sources([a,b,c,d]),["b","d"])
        self.assertEqual(select_six_hop_sources([a,b,c]),["b","c"])
        self.assertEqual(select_six_hop_sources([a,b]),["b","a"])
        a["source_account_footprint"]["broadcast"]=True
        with self.assertRaises(ValueError):select_six_hop_sources([a,b])
    def test_execution_summary_distinguishes_missing_and_mismatch(self):
        from arb.blockzilla_multihop import execution_pricing_summary
        samples=[{"venue":"orca","execution_clock_leg_comparison":{"modeled_output":100,"delta":0}},
                 {"venue":"orca","execution_clock_leg_comparison":{"modeled_output":100,"delta":-1}},
                 {"venue":"orca","execution_clock_leg_comparison":None}]
        self.assertEqual(execution_pricing_summary([{"audit":{"native_leg_samples":samples}}])["orca"],
            {"samples":3,"predicted":2,"matches":1,"blocked":1})
if __name__=="__main__":unittest.main()
