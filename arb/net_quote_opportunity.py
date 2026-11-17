"""Conservative, source-mint-denominated *indicative* route cost gate.

No automatic SOL/USDC conversions, zero-cost defaults, live execution,
or claim of realized net profit. Venue swap fees are already included in
source quote outputs; these fields cover EXTRA costs only.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
COST_KEYS=("network_fee","priority_fee","account_setup","slippage_reserve")


def evaluate(gross_row,costs,*,observed_unix):
    """Return an indicative net result only with complete coherent cost inputs."""
    base={"status":"NET_COST_UNASSESSABLE","estimated_net_positive":False,
          "net_profitability_confirmed":False,
          "signed_atomic_execution_verified":False,**SAFE}
    if not isinstance(gross_row,dict) or gross_row.get("status")!="GROSS_INDICATIVE_ONLY":
        return {**base,"reason":"source-bound gross quote unavailable"}
    if not isinstance(costs,dict):
        return {**base,"reason":"complete start-mint cost estimate missing"}
    if (type(observed_unix)is not int or observed_unix<0 or
            type(costs.get("observed_unix")) is not int or
            abs(observed_unix-costs["observed_unix"])>60):
        return {**base,"reason":"missing or stale cost observation"}
    if (costs.get("start_mint")!=gross_row.get("start_mint") or
            costs.get("units")!="START_MINT_BASE_UNITS"):
        return {**base,"reason":"cost currency or denomination mismatch"}
    slots={leg.get("source_slot") for leg in gross_row.get("quotes",[])}
    if (len(slots)!=1 or type(next(iter(slots)))is not int or
            costs.get("snapshot_slot")!=next(iter(slots))):
        return {**base,"reason":"cost snapshot and source quote mismatch"}
    if (not isinstance(costs.get("estimation_method"),str)
            or not costs["estimation_method"]):
        return {**base,"reason":"missing cost provenance"}
    if any(key in costs and costs[key] is not False for key in SAFE):
        return {**base,"reason":"unsafe cost authority assertion"}
    if any(type(costs.get(key)) is not int or
           not 0<=costs[key]<2**64 for key in COST_KEYS):
        return {**base,"reason":"missing or invalid explicit cost component"}
    if all(costs[key]==0 for key in COST_KEYS):
        return {**base,"reason":"all-zero cost evidence is not credible"}
    gross=gross_row.get("gross_delta_start_mint_base_units")
    if type(gross)is not int:
        return {**base,"reason":"invalid gross output"}
    total=sum(costs[key] for key in COST_KEYS)
    if total>=2**64:
        return {**base,"reason":"cost aggregate overflow"}
    net=gross-total
    return {"status":"ESTIMATED_NET_POSITIVE_UNVERIFIED" if net>0
                 else "ESTIMATED_NET_NONPOSITIVE_UNVERIFIED",
            "start_mint":gross_row["start_mint"],
            "gross_delta_start_mint_base_units":gross,
            "estimated_additional_cost_start_mint_base_units":total,
            "estimated_net_delta_start_mint_base_units":net,
            "estimated_net_positive":net>0,
            "cost_estimation_method":costs["estimation_method"],
            "net_profitability_confirmed":False,
            "signed_atomic_execution_verified":False,**SAFE}
