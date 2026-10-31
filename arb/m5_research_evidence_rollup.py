"""Aggregate accepted signed research coverage, pricing gaps, and gross risk.

Only consume offline source and receipt reports. This is evidence reporting,
not a price oracle or net-profit approval.
"""
from collections import Counter
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def summarize(source_summary, signed_summary, parity_reports, economics_reports):
    if not isinstance(source_summary,dict) or not isinstance(signed_summary,dict):
        raise ValueError("source and signed summaries required")
    accepted=[r for r in signed_summary.get("routes",[])
              if r.get("independent_signed_accepted") is True]
    triples=set()
    venues=set()
    for row in accepted:
        route=row.get("route_venues")
        if not isinstance(route,list) or len(route)!=3 or len(set(route))!=3:
            raise ValueError("accepted signed route lacks three distinct venues")
        triples.add(tuple(sorted(route)))
        venues.update(route)
    quote_status=Counter()
    priced=0
    compared=0
    exact_diagnostic_matches=0
    for report in parity_reports:
        if not isinstance(report,dict) or report.get("signed_execution_accepted") is not True:
            continue
        for leg in report.get("leg_comparisons",[]):
            if not isinstance(leg,dict):
                raise ValueError("invalid signed leg quote diagnostic")
            compared+=1
            if leg.get("quoted_output_base_units") is not None:
                priced+=1
                if leg.get("deviation_bps")==0:
                    exact_diagnostic_matches+=1
            else:
                quote_status[str(leg.get("reason") or "UNSPECIFIED_QUOTE_BLOCKER").split(":")[0]]+=1
    gross=[]
    economic_blockers=Counter()
    for item in economics_reports:
        if not isinstance(item,dict):
            continue
        if type(item.get("gross_delta_start_mint_base_units")) is int:
            gross.append(item["gross_delta_start_mint_base_units"])
        if item.get("status")=="COST_EVIDENCE_BLOCKED":
            economic_blockers[item.get("reason","UNSPECIFIED_COST_EVIDENCE")]+=1
    return {"signed_accepted_routes":len(accepted),
            "distinct_accepted_venue_triples":len(triples),
            "distinct_accepted_venues":sorted(venues),
            "authenticated_source_export_count":source_summary.get("exported"),
            "attempted_route_count":signed_summary.get("attempted"),
            "signed_quote_leg_count":compared,
            "indicative_priced_legs":priced,
            "exact_integer_indicative_matches_not_proof":exact_diagnostic_matches,
            "missing_quote_leg_reasons":dict(quote_status),
            "signed_gross_start_mint_deltas":gross,
            "cost_blocker_counts":dict(economic_blockers),
            "independently_validated_quote_samples":0,
            "independently_verified_net_profit_routes":0,**SAFE}
