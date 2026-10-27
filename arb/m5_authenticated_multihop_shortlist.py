"""Prioritize authenticated multihop route candidates without inventing quotes.

A route is a *topological research lead* only; no profitability claim.
"""
from collections import Counter
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def shortlist(report, *, maximum=20):
    if (not isinstance(report,dict) or any(report.get(k)is not False for k in SAFE)
            or type(maximum)is not int or not 1<=maximum<=100):
        raise ValueError("invalid authenticated source candidate report")
    routes=report.get("routes")
    if not isinstance(routes,list) or len(routes)>2000:
        raise ValueError("invalid bounded cycle inventory")
    scored=[]
    for idx,r in enumerate(routes):
        legs=r.get("legs")
        if (not isinstance(legs,list) or not 2<=len(legs)<=6
                or r.get("hops")!=len(legs)):
            raise ValueError("malformed authenticated cycle")
        if any(not isinstance(l,dict) or not l.get("pool") or not l.get("venue") for l in legs):
            raise ValueError("route pool identities absent")
        mint=r.get("start_mint")
        current=mint
        for leg in legs:
            if leg.get("input")!=current:raise ValueError("route mint discontinuity")
            current=leg.get("output")
        if current!=mint:raise ValueError("route not closed")
        venues={x["venue"] for x in legs}
        scored.append({"source_graph_route_index":idx,"hops":len(legs),
                       "distinct_venue_count":len(venues),
                       "start_mint":mint,"pool_addresses":[l["pool"] for l in legs],
                       "venues":[l["venue"] for l in legs],
                       "status":"SOURCE_AUTHENTICATED_UNQUOTED",
                       "source_quote_verified":False,
                       "signed_simulation_verified":False,**SAFE})
    # Coverage rather than raw route count: prioritize longer routes and
    # diverse venue combinations, avoid spending all slots on near-duplicates.
    scored.sort(key=lambda r:(-r["hops"],-r["distinct_venue_count"],r["source_graph_route_index"]))
    chosen=[];seen_venue_sequences=set()
    for row in scored:
        k=(row["hops"],tuple(row["venues"]))
        if k not in seen_venue_sequences:
            chosen.append(row);seen_venue_sequences.add(k)
            if len(chosen)==maximum:break
    for row in scored:
        if len(chosen)==maximum:break
        if row not in chosen:chosen.append(row)
    return {"status":"AUTHENTICATED_TOPOLOGY_ONLY",
            "total_source_cycles":len(routes),
            "cycle_inventory_truncated":report.get("cycle_inventory_truncated"),
            "selected":chosen,
            "selected_by_hops":dict(sorted(Counter(str(r["hops"]) for r in chosen).items())),
            "native_quoted_count":0,"net_profitable_count":0,**SAFE}

def main():
    import argparse,json
    from pathlib import Path
    p=argparse.ArgumentParser()
    p.add_argument("--graph",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--maximum",type=int,default=20)
    a=p.parse_args()
    out=shortlist(json.loads(Path(a.graph).read_text()),maximum=a.maximum)
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n")
    print(json.dumps({k:out[k] for k in ("status","total_source_cycles","selected_by_hops","native_quoted_count","broadcast")}))
if __name__=="__main__":main()
