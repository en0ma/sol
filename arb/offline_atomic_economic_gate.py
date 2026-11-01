"""Strict offline economic audit gate for a complete signed atomic route.

No budget assumptions, guessed token/SOL conversion or historical unrelated
fees are permitted to stand in for the actual signed transaction's paid fee.
For unsent offline transactions, paid fee is inherently unavailable: report
a prospective fee quote separately and never mark net independently verified.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def audit_complete_atomic_economics(route, signed, quote_chain, fee):
    if not all(isinstance(x,dict) for x in (route,signed,quote_chain,fee)):
        raise ValueError("complete route and signed evidence objects required")
    legs=route.get("legs")
    if not isinstance(legs,list) or not 2<=len(legs)<=6:
        raise ValueError("2..6 leg atomic route required")
    if (signed.get("signed_atomic_execution_verified") is not True
        or signed.get("independent_spl_poststate_verified") is not True
        or signed.get("rollback_control_verified") is not True
        or signed.get("offline_only") is not True
        or signed.get("broadcast") is not False):
        return {"status":"ATOMIC_SIGNED_EVIDENCE_INCOMPLETE",
                "net_base_units":None,"net_profitability_verified":False,**SAFE}
    if (quote_chain.get("status")!="COMPLETE_QUOTE_CHAIN_ARITHMETIC_ONLY"
        or len(quote_chain.get("legs",[]))!=len(legs)
        or quote_chain.get("native_quote_authenticity_established_here") is not False):
        raise ValueError("nonmatching or falsely attested native quote chain")
    gross=signed.get("gross_start_mint_base_units")
    if type(gross)is not int:
        raise ValueError("signed start-mint gross delta missing")
    # No actual fee was paid for an offline-only unsent transaction. It is
    # invalid to upgrade an unrelated confirmed historical fee as its fee.
    return {"status":"OFFLINE_ATOMIC_GROSS_ONLY_UNPAID_FEE",
            "gross_start_mint_base_units":gross,
            "native_quote_parity_independently_verified":False,
            "independent_actual_fee_paid":False,
            "fee_quote_diagnostic":fee.get("quoted_fee_lamports"),
            "net_base_units":None,
            "net_profitability_verified":False,**SAFE}

def screen_prospective_atomic_cost_budget(route, signed, quote_chain,
                                          cost_components):
    """Reconcile all prospective route costs in start-mint raw units.

    A real offline signed transaction paid no chain fee. Thus even a complete
    and positive estimated budget cannot be called settled P&L. We intentionally
    keep all six cost categories explicit and require an independent provenance
    label for each submitted estimate, rather than treating missing as zero.
    This is budget arithmetic, never a fee-paid verifier.
    """
    base=audit_complete_atomic_economics(
        route,signed,quote_chain,{"quoted_fee_lamports":None})
    if (base["status"]!="OFFLINE_ATOMIC_GROSS_ONLY_UNPAID_FEE"
        or not isinstance(cost_components,dict)):
        return {**base,"prospective_net_base_units":None,
                "cost_budget_status":"UNASSESSABLE"}
    required=("network_fee","priority_fee","compute_cost","rent",
              "borrow_cost","tip")
    if set(cost_components)!=set(required):
        raise ValueError("all six independent prospective costs required")
    start=route.get("start_mint")
    if not isinstance(start,str) or not start:
        raise ValueError("canonical starting mint required")
    components={}
    total=0
    for category in required:
        value=cost_components[category]
        if (not isinstance(value,dict)
            or type(value.get("amount_start_mint_base_units")) is not int
            or not 0<=value["amount_start_mint_base_units"]<2**64
            or value.get("start_mint")!=start
            or not isinstance(value.get("observation_id"),str)
            or not value["observation_id"]):
            raise ValueError("invalid or unconverted prospective cost component")
        # An observation ID is a trace label, not an authenticated receipt.
        # Never accept an asserted paid-fee flag from the cost provider.
        if (value.get("actual_fee_paid_verified") is not False
            or value.get("broadcast") is not False):
            raise ValueError("cost observation claims settlement or broadcast")
        amount=value["amount_start_mint_base_units"]
        total+=amount
        if total>=2**64:
            raise ValueError("prospective cost budget exceeds start-mint u64")
        components[category]={"amount_start_mint_base_units":amount,
                              "observation_id":value["observation_id"]}
    gross=base["gross_start_mint_base_units"]
    return {**base,"cost_budget_status":"PROSPECTIVE_ONLY_UNPAID",
            "prospective_costs_start_mint_base_units":components,
            "prospective_total_cost_start_mint_base_units":total,
            "prospective_net_base_units":gross-total,
            "costs_independently_proven_as_paid":False,
            "independent_actual_fee_paid":False,
            "net_base_units":None,"net_profitability_verified":False,**SAFE}
