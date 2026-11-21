"""Exact-unit, evidence-bounded 2–6-leg offline route economics.

Never estimates unknown SOL->start-mint conversion. The function is an
arithmetic cross-check of independent signed observations, NOT proof that
the underlying observations are authentic or a live-tradable opportunity.
"""
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
UINT64=2**64


# Canonical wrapped SOL mint: 1 lamport is exactly 1 raw WSOL base unit.
# This identity is not a market quote and cannot be used for other mints.
WRAPPED_SOL_MINT="So11111111111111111111111111111111111111112"
SOL_FEE_FIELDS=("network_fee","priority_fee","tip")


def reconcile_wsol_lamport_costs(observation):
    """Check independently supplied lamport fees against same-unit cost rows.

    A caller's boolean attestations are not independent evidence by themselves:
    only an external signed-transaction/fee auditor may set them. This routine
    enforces a strict numerical identity, not signature/fee authenticity.
    """
    if not isinstance(observation,dict):
        raise ValueError("cost observation required")
    if observation.get("start_mint")!=WRAPPED_SOL_MINT:
        raise ValueError("lamport identity available only for canonical WSOL")
    lamports=observation.get("independently_audited_sol_fee_lamports")
    costs=observation.get("verified_costs_start_mint_base_units")
    if (observation.get("independent_sol_fee_audit_verified") is not True or
        not isinstance(lamports,dict) or set(lamports)!=set(SOL_FEE_FIELDS) or
        not isinstance(costs,dict)):
        raise ValueError("independent SOL fee inventory unavailable")
    for field in SOL_FEE_FIELDS:
        amount=lamports[field]
        if (type(amount)is not int or not 0<=amount<UINT64 or
                type(costs.get(field))is not int or costs[field]!=amount):
            raise ValueError("signed SOL fee / WSOL base-unit disagreement: "+field)
    return {"status":"WSOL_LAMPORT_IDENTITY_RECONCILED_NOT_FEE_AUTHENTICATION",
            "wsol_fee_base_units":sum(lamports.values()),**SAFE}


def assess_offline_cycle_costs(observation):
    """Return gross and possible net arithmetic only when all costs are known.

    Inputs in the *same start-mint raw base unit*. The caller must retain
    original cryptographic signed receipts and verify them independently.
    """
    if not isinstance(observation,dict):
        raise ValueError("signed observation object required")
    legs=observation.get("legs")
    start=observation.get("start_mint")
    initial=observation.get("initial_base_units")
    terminal=observation.get("terminal_base_units")
    if (type(legs)is not int or not 2<=legs<=6 or
        not isinstance(start,str) or not start or
        type(initial)is not int or not 0<initial<UINT64 or
        type(terminal)is not int or not 0<=terminal<UINT64 or
        observation.get("independent_signed_accepted") is not True or
        observation.get("closed_route_verified") is not True or
        observation.get("signed_cpi_per_leg_verified") is not True or
        observation.get("signed_spl_poststate_verified") is not True or
        observation.get("rollback_control_verified") is not True or
        observation.get("offline_only") is not True or
        any(observation.get(k) is not False for k in SAFE)):
        raise ValueError("incomplete independently accepted offline cycle evidence")
    gross=terminal-initial
    # These components must be wholly denominated in start-mint base units,
    # including the fee incurred in SOL. Zero must be explicit, not assumed.
    names=("network_fee","priority_fee","setup_rent_net","flash_loan_fee",
           "tip","other")
    costs=observation.get("verified_costs_start_mint_base_units")
    converted=observation.get("network_fee_conversion_independently_verified")
    items=None
    if converted is True and isinstance(costs,dict) and set(costs)==set(names):
        if all(type(costs[k]) is int and 0<=costs[k]<UINT64 for k in names):
            items={k:costs[k] for k in names}
    # When explicit signed SOL fee evidence is provided, do not allow a
    # caller to substitute different WSOL amounts and still claim net math.
    if observation.get("independently_audited_sol_fee_lamports") is not None:
        try:
            reconcile_wsol_lamport_costs(observation)
        except ValueError:
            items=None
    if items is None:
        return {"status":"SIGNED_GROSS_ONLY_COST_CONVERSION_BLOCKED",
                "legs":legs,"start_mint":start,
                "observed_gross_base_units":gross,
                "net_base_units":None,"costs_verified":False,
                "net_positive_arithmetic":None,**SAFE}
    total=sum(items.values())
    # Individually valid u64 cost fields can still sum beyond the u64
    # start-mint accounting domain. Never promote that malformed budget.
    if total>=UINT64:
        return {"status":"SIGNED_GROSS_ONLY_COST_SUM_OVERFLOW_BLOCKED",
                "legs":legs,"start_mint":start,
                "observed_gross_base_units":gross,
                "net_base_units":None,"costs_verified":False,
                "net_positive_arithmetic":None,**SAFE}
    net=gross-total
    return {"status":"OFFLINE_SIGNED_NET_ARITHMETIC_ONLY",
            "legs":legs,"start_mint":start,
            "observed_gross_base_units":gross,
            "total_verified_cost_base_units":total,
            "net_base_units":net,"costs_verified":True,
            "net_positive_arithmetic":net>0,
            "future_live_profitability_verified":False,**SAFE}
