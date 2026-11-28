import unittest
from arb.blockzilla_size_plan import GRID,select_sizes,CONTROL_AMOUNTS
from arb.meteora_dlmm_bin_quote import quote_bins,Q
from arb.meteora_dlmm_source_bin_decoder import directional_bins

class SizeAndTraversalTests(unittest.TestCase):
    def test_size_selection_preserves_controls_and_maximum_stress(self):
        samples=[{"amount":a,"status":"COMPLETE_RESEARCH_MODEL",
                  "gross_delta":-a//100,"estimated_net":-5000-a//100} for a in GRID]
        chosen=select_sizes(samples)
        self.assertEqual([r["amount"] for r in chosen],[10000,30000000])
        self.assertFalse(set(CONTROL_AMOUNTS)&{r["amount"] for r in chosen})
        samples[-1]["status"]="MODEL_BLOCKED"
        self.assertEqual(select_sizes(samples)[-1]["amount"],10000000)
        with self.assertRaises(ValueError):select_sizes(samples[:-1])
    def test_no_additional_complete_size(self):
        samples=[{"amount":a,"status":"MODEL_BLOCKED"} for a in GRID]
        self.assertEqual(select_sizes(samples),[])
    def test_three_array_bound_and_no_gap_crossing(self):
        def arr(a):
            return {"source_account_verified":True,"bins":[
                {"bin_id":i,"amount_x":10,"amount_y":10,"price_q64":Q}
                for i in range(a,a+70)]}
        rows=directional_bins([arr(0),arr(70),arr(140)],active_id=0,x_to_y=False,maximum_bins=210)["bins"]
        self.assertEqual(len(rows),210)
        self.assertEqual(quote_bins(amount_in=1000,swap_x_for_y=False,bins=rows,
            total_fee_rate=0,max_bins=210)["amount_out"],1000)
        gap=directional_bins([arr(0),arr(140)],active_id=0,x_to_y=False,maximum_bins=210)["bins"]
        self.assertEqual(len(gap),70)
        with self.assertRaises(ValueError):
            quote_bins(amount_in=1000,swap_x_for_y=False,bins=gap,total_fee_rate=0,max_bins=210)
    def test_matching_limit_order_cannot_be_skipped(self):
        rows=[{"bin_id":i,"amount_x":10,"amount_y":10,"price_q64":Q,
               "open_order_amount":5,"processed_order_remaining_amount":0,
               "limit_order_ask_side":1} for i in range(2)]
        self.assertEqual(quote_bins(amount_in=5,swap_x_for_y=False,bins=rows,
            total_fee_rate=0,limit_order_support=True)["amount_out"],5)
        with self.assertRaisesRegex(ValueError,"matching limit-order"):
            quote_bins(amount_in=11,swap_x_for_y=False,bins=rows,total_fee_rate=0,limit_order_support=True)
        self.assertEqual(quote_bins(amount_in=11,swap_x_for_y=False,bins=rows,
            total_fee_rate=0,limit_order_support=False)["amount_out"],11)
    def test_comparable_ranking_separates_mints_and_amounts(self):
        from arb.blockzilla_size_plan import rank_comparable_grid,WSOL,SAFE
        def plan(mint,slot,gross):
            return {"status":"SOURCE_NATIVE_BOUNDED_SIZE_PLAN","start_mint":mint,
                "source_slot":slot,"signed_amounts":list(CONTROL_AMOUNTS),
                "samples":[{"amount":a,"status":"COMPLETE_RESEARCH_MODEL",
                    "output":a+gross,"gross_delta":gross,
                    "estimated_message_fee":5000 if mint==WSOL else None,
                    "estimated_net":gross-5000 if mint==WSOL else None} for a in GRID],**SAFE}
        plans={"a":plan(WSOL,12,-10),"b":plan(WSOL,17,-2),"c":plan("OTHER",20,99)}
        ranked=rank_comparable_grid(plans)
        self.assertEqual(len(ranked),16)
        sol=next(g for g in ranked if g["start_mint"]==WSOL)
        self.assertEqual([r["id"] for r in sol["routes"]],["b","a"])
        self.assertEqual(sol["source_slot_range"],[12,17])
        self.assertFalse(sol["simultaneous_source_snapshot"])
        plans["a"]["samples"][0]["estimated_net"]=999
        with self.assertRaisesRegex(ValueError,"economic identity"):
            rank_comparable_grid(plans)
    def test_priced_six_hop_selection_keeps_footprint_class_and_controls(self):
        from arb.blockzilla_size_plan import select_priced_six_hop_sources,WSOL,SAFE
        def candidate(rid,keys,complete):
            row={"id":rid,"source_slot":1,"source_clock":{"unix_timestamp":2},
                 "start_mint":WSOL,"source_account_footprint":{
                    "resolved_account_key_estimate":keys,"manifest_sha256":rid,
                    "status":"SOURCE_UNSIGNED_INSTRUCTION_KEY_UNION",**SAFE}}
            samples=[{"amount":a,"status":"COMPLETE_RESEARCH_MODEL" if a in complete else "MODEL_BLOCKED",
                "output":a-1,"gross_delta":-1,"estimated_message_fee":5000,"estimated_net":-5001}
                for a in GRID]
            chosen=select_sizes(samples)
            plan={"status":"SOURCE_NATIVE_BOUNDED_SIZE_PLAN","source_slot":1,
                "source_unix":2,"manifest_sha256":rid,"start_mint":WSOL,
                "samples":samples,"complete_models":len(complete),"selected":chosen,
                "signed_amounts":list(CONTROL_AMOUNTS)+[s["amount"] for s in chosen],
                "net_profit_verified":False,**SAFE}
            return row,plan
        pairs=[candidate("a",60,[]),candidate("b",63,GRID),
               candidate("c",66,GRID),candidate("d",61,CONTROL_AMOUNTS)]
        rows=[r for r,_ in pairs];plans={r["id"]:p for r,p in pairs}
        result=select_priced_six_hop_sources(rows,plans)
        self.assertEqual(result["footprint_only_ids"],["a","b"])
        self.assertEqual(result["selected_ids"],["b","d"])
        self.assertFalse(result["signed_results_used"])
        self.assertFalse(result["net_profit_verified"])
        self.assertEqual(select_priced_six_hop_sources(rows[:1],{"a":plans["a"]})["selected_ids"],["a"])
        plans["b"]["complete_models"]=99
        with self.assertRaisesRegex(ValueError,"size coverage"):
            select_priced_six_hop_sources(rows,plans)
        plans["b"]["complete_models"]=len(GRID)
        plans["b"]["manifest_sha256"]="other"
        with self.assertRaisesRegex(ValueError,"source identity"):
            select_priced_six_hop_sources(rows,plans)
if __name__=="__main__":unittest.main()
