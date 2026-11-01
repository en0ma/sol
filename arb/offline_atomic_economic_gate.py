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
