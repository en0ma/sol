"""Independent four-to-six-hop signed handoff eligibility for M5.

A source capture is never itself a signed transaction or rollback receipt.
Only an independently accepted result from the existing universal coordinator
can satisfy execution evidence. Report blockers before any local simulation.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def assess(fixture,*,quote_report=None,signed_audit=None):
    verify(fixture)
    if fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE":
        raise ValueError("authenticated four-to-six source fixture required")
    rows=extract_pool_states(fixture)
    if not 4<=len(rows)<=6:
        raise ValueError("four-to-six actual native source legs missing")
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe captured source route")
    if isinstance(quote_report,dict) and any(quote_report.get(k) is not False for k in SAFE):
        raise ValueError("unsafe or unverifiable native quote handoff")
    if isinstance(signed_audit,dict) and any(signed_audit.get(k) is not False for k in SAFE):
        raise ValueError("unsafe signed simulation audit handoff")
    issues=[]
    # An indicative amount chain can help diagnose signing readiness, but
    # cannot authorize an execution attempt or be mistaken for exact prices.
    chain_trace=quote_report.get("quoted_legs") if isinstance(quote_report,dict) else None
    if isinstance(chain_trace,list) and chain_trace:
        if len(chain_trace)!=len(rows) or any(
                not isinstance(leg,dict) or leg.get("index")!=i or
                leg.get("venue")!=row["venue"] or leg.get("pool")!=row["address"] or
                leg.get("source_slot")!=fixture["state_accounts_observed_slot"] or
                type(leg.get("input_base_units"))is not int or
                type(leg.get("output_base_units"))is not int or
                leg["input_base_units"]<=0 or leg["output_base_units"]<=0 or
                (i>0 and leg["input_base_units"]!=chain_trace[i-1]["output_base_units"])
                for i,(leg,row) in enumerate(zip(chain_trace,rows))):
            issues.append("native route leg amounts or source identities inconsistent")
    else:
        issues.append("complete source-bound four-to-six leg amount trace missing")
    if (not isinstance(quote_report,dict) or
            quote_report.get("source_quote_verified") is not True or
            quote_report.get("protocol_exact_verified") is not True or
            quote_report.get("snapshot_slot")!=fixture["state_accounts_observed_slot"] or
            quote_report.get("hops")!=len(rows)):
        issues.append("same-slot protocol-exact native route quotes missing")
    # The existing three-leg coordinator receipts cannot be reused as an
    # independent signed four-hop acceptance result.
    if (not isinstance(signed_audit,dict) or
            signed_audit.get("status")!="VERIFIED_SIGNED_FOUR_TO_SIX_HOP_ROLLBACK" or
            signed_audit.get("signed_atomic_simulation_verified") is not True or
            signed_audit.get("rollback_failure_case_verified") is not True or
            signed_audit.get("route_pool_addresses")!=fixture["route_pool_addresses"] or
            signed_audit.get("snapshot_slot")!=fixture["state_accounts_observed_slot"]):
        issues.append("independent four-to-six-hop signed CPI/SPL and rollback receipt missing")
    # The coordinator cannot safely sign against a hypothetical net-positive
    # output when actual fees are not converted into the starting mint.
    if (not isinstance(quote_report,dict) or
            type(quote_report.get("estimated_cost_start_mint_base_units")) is not int or
            quote_report.get("estimated_cost_start_mint_base_units",0)<0 or
            quote_report.get("net_profit_verified") is not True):
        issues.append("starting-mint total cost and net economics not verified")
    # Execution should NOT be classified accepted by an arbitrary flags-only
    # object; until an independent 4–6-hop auditor is wired, always block.
    issues.append("independent four-to-six-hop acceptance auditor not yet integrated")
    return {"status":"FOUR_TO_SIX_HOP_SIGNED_HANDOFF_BLOCKED",
            "hops":len(rows),"source_slot":fixture["state_accounts_observed_slot"],
            "route_venues":[r["venue"] for r in rows],
            "blockers":issues,"signed_handoff_ready":False,
            "source_route_pool_addresses":fixture["route_pool_addresses"],
            "independently_signed_verified":False,
            "net_profit_verified":False,**SAFE}


def execute_prepared_offline(rpc, fixture, quote_report, preparation):
    """Execute this exact source graph route through the existing N-leg auditor.

    Preparation is in-memory only: a real ephemeral offline signer, funded
    user SPL accounts, venue-specific authenticated builder state/evidence,
    and a negative final-instruction mutation callback. Never serialize signer
    keys to source manifests or infer preparation from indicative quotes.
    The coordinator must independently verify actual signed CPI/SPL and
    negative rollback; returned source identity is an input binding, not a
    cryptographic claim about upstream state or mainnet settlement.
    """
    from arb.pumpswap_local_simulation import local_rpc_only
    from arb.atomic_graph_coordinator import coordinate_registered_cycle_offline
    local_rpc_only(rpc)
    verify(fixture)
    if fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE":
        raise ValueError("actual authenticated graph source fixture required")
    if not isinstance(preparation,dict) or any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("explicit safe offline signed preparation required")
    rows=extract_pool_states(fixture)
    if not 4<=len(rows)<=6 or not isinstance(quote_report,dict):
        raise ValueError("native 4-6-leg quote trace required")
    if (quote_report.get("status")!="SOURCE_BOUND_INDICATIVE_CHAIN_NOT_EXECUTION_VERIFIED"
        or quote_report.get("hops")!=len(rows)
        or quote_report.get("indicative_all_legs") is not True
        or any(quote_report.get(k) is not False for k in SAFE)):
        raise ValueError("complete safe source-native quote observation required")
    trace=quote_report.get("quoted_legs")
    source_slot=fixture.get("state_accounts_observed_slot")
    mints=fixture.get("route_mints")
    if (type(source_slot) is not int or source_slot<0
        or not isinstance(trace,list) or len(trace)!=len(rows)
        or not isinstance(mints,list) or len(mints)!=len(rows)+1
        or mints[0]!=mints[-1]):
        raise ValueError("source slot and closed quote identities required")
    amount=quote_report.get("input_base_units")
    if type(amount) is not int or not 0<amount<2**64:
        raise ValueError("invalid source-native initial exact input")
    legs=[]
    for index,(row,q) in enumerate(zip(rows,trace)):
        if (not isinstance(q,dict) or q.get("index")!=index
            or q.get("venue")!=row["venue"] or q.get("pool")!=row["address"]
            or q.get("source_slot")!=source_slot
            or type(q.get("input_base_units")) is not int
            or q["input_base_units"]!=amount
            or type(q.get("output_base_units")) is not int
            or not 0<q["output_base_units"]<2**64):
            raise ValueError("native quote trace is not bound to this source route")
        legs.append({"venue":row["venue"],"pool":row["address"],
                     "input_mint":mints[index],"output_mint":mints[index+1]})
        amount=q["output_base_units"]
    if (amount!=quote_report.get("output_base_units")
        or quote_report.get("gross_delta_start_mint_base_units")!=
           amount-quote_report["input_base_units"]):
        raise ValueError("source quote terminal and gross identity mismatch")
    required=("states","evidence","owner","token_accounts","signer",
              "negative_instructions")
    if any(key not in preparation for key in required):
        raise ValueError("offline signer, user accounts and negative control missing")
    registry={"pools":[{"venue":row["venue"],"address":row["address"],
                         "mints":row["mints"]} for row in rows]}
    route={"start_mint":mints[0],"legs":legs}
    result=coordinate_registered_cycle_offline(
        rpc,registry,route,preparation["states"],preparation["evidence"],
        preparation["owner"],preparation["token_accounts"],
        quote_report["input_base_units"],preparation["signer"],
        negative_instructions=preparation["negative_instructions"],
        observe=preparation.get("observe"))
    receipt=result.get("signed_receipt")
    verified=(isinstance(receipt,dict)
        and receipt.get("status")=="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"
        and receipt.get("signed_packet_crypto_bound") is True
        and receipt.get("signed_cpi_per_leg_verified") is True
        and receipt.get("rollback_failure_case_verified") is True
        and receipt.get("signed_atomic_simulation_verified") is True
        and result.get("signed_atomic_simulation_verified") is True
        and all(receipt.get(k) is False for k in SAFE))
    if not isinstance(receipt,dict) or any(result.get(k) is not False for k in SAFE):
        raise ValueError("unsafe signed coordinator result")
    return {"status":("GRAPH_SOURCE_SIGNED_ATOMIC_OFFLINE_VERIFIED"
                      if verified else "GRAPH_SOURCE_SIGNED_ATOMIC_UNVERIFIED"),
            "source_snapshot_slot":source_slot,
            "source_manifest_sha256":fixture.get("state_account_manifest_sha256"),
            "route_venues":fixture["route_venues"],
            "route_pool_addresses":fixture["route_pool_addresses"],
            "route_mints":mints,
            "signed_receipt":receipt,
            "observed_signed_economics":result.get("observed_signed_economics"),
            "signed_atomic_simulation_verified":verified,
            "independent_source_consensus_root_verified":False,
            "quote_accuracy_verified":False,
            "net_profitability_verified":False,**SAFE}
