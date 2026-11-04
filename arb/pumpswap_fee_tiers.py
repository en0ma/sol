"""PumpSwap canonical/noncanonical fee tier selection from official fee guide.

Reference: pump-fun/pump-public-docs/docs/FEE_PROGRAM_README.md.
Inputs must be sourced from validated accounts; this pure selection function
does NOT establish FeeConfig authenticity, token supply, actual swap rounding
or simulation validity. No default tiers or rates are invented.
"""


def select_fee_tier(fee_config, *, canonical, base_mint_supply, base_reserve,
                    quote_reserve):
    if type(canonical) is not bool or not isinstance(fee_config, dict):
        raise ValueError("verified canonical status and FeeConfig required")
    if (any(type(x) is not int for x in
            (base_mint_supply, base_reserve, quote_reserve))
            or min(base_mint_supply, base_reserve, quote_reserve) <= 0):
        raise ValueError("positive integer reserves and mint supply required")
    def rates(fees):
        if not isinstance(fees, dict):
            raise ValueError("incomplete fee rates")
        names=("lp_fee_bps", "protocol_fee_bps", "creator_fee_bps")
        if any(type(fees.get(k)) is not int or not 0 <= fees[k] <= 10000
               for k in names):
            raise ValueError("invalid fee rates")
        if sum(fees[k] for k in names) >= 10000:
            raise ValueError("fees consume entire swap")
        return {k:fees[k] for k in names}
    market_cap=quote_reserve*base_mint_supply//base_reserve
    if not canonical:
        selected=rates(fee_config.get("flat_fees"))
        return {"fee_rates": selected,"market_cap_quote_base_units":market_cap,
                "selection": "NONCANONICAL_FLAT", "source_verified":False}
    tiers=fee_config.get("fee_tiers")
    if not isinstance(tiers,list) or not tiers:
        raise ValueError("canonical pool requires fee tiers")
    last=-1
    selected=None
    for entry in tiers:
        if not isinstance(entry,dict):
            raise ValueError("invalid fee tier")
        threshold=entry.get("market_cap_threshold")
        if type(threshold) is not int or threshold < 0 or threshold <= last:
            raise ValueError("unsorted or invalid fee tier thresholds")
        last=threshold
        value=rates(entry.get("fees"))
        if selected is None or market_cap >= threshold:
            selected=value
    return {"fee_rates":selected,"market_cap_quote_base_units":market_cap,
            "selection":"CANONICAL_MARKET_CAP_TIER","source_verified":False}
