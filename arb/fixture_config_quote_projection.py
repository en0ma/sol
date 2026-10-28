"""Account-derived CPMM and CLMM quote-state projection from captured fixtures.

The native pool and vault fundamentals and fee config must share a manifest-
bound captured account inventory. CLMM tick boundaries remain unavailable.
CPMM creator-fee pools cannot be quoted with trade-fee-only economics.
"""
from arb.fixture_pool_fundamentals import extract
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.authenticated_quote_provider import from_snapshot
from arb.cpmm_quote import quote_fee_rounding_interval,quote_native_fee_candidates
from arb.cpmm_creator_fee_quote import calculate as creator_quote, effective_reserves
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def derive(fixture,*,observed_unix):
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("valid observed time required")
    pool_states=extract_pool_states(fixture)
    native=extract(fixture)["fundamentals"]
    kind=fixture.get("fixture_kind")
    if kind=="THREE_DISTINCT_VENUE_CLOSED_ROUTE":
        n=3
    elif kind=="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE":
        route=fixture.get("route_pool_addresses")
        n=len(route) if isinstance(route,list) else 0
        if (not 4<=n<=6 or
                any(fixture.get(k)is not False for k in SAFE) or
                len(set(route))!=n):
            raise ValueError("authenticated 4–6-hop source pool inventory required")
        if fixture.get("state_accounts_observed_slot") is None:
            raise ValueError("four-to-six-hop source context slot missing")
    else:
        n=2
    if len(native)!=n or len(pool_states)!=n:
        raise ValueError("source-bound pool inventory size mismatch")
    source_ids=[(item["venue"],item["address"]) for item in pool_states]
    native_ids=[(item["venue"],item["address"]) for item in native]
    if len(set(source_ids))!=n or len(set(native_ids))!=n or set(source_ids)!=set(native_ids):
        raise ValueError("native vault fundamentals and decoded pool identities diverge")
    native_by_id={(item["venue"],item["address"]):item for item in native}
    outputs=[];blocked=[]
    for item in pool_states:
        fundamentals=native_by_id[(item["venue"],item["address"])]
        if (fundamentals["mints"]!=item["mints"] or
                fundamentals["snapshot_slot"]!=item["snapshot_slot"]):
            raise ValueError("native fundamentals source mint or slot mismatch")
        venue=item["venue"]
        row={"venue":venue,"address":item["address"],
             "mints":item["mints"],"slot":item["snapshot_slot"],
             "observed_unix":observed_unix,
             "source_authenticated":True,"verified":True,
             "account_owner_verified":True,
             "snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL",
             "vault_base_units":fundamentals["vault_base_units"]}
        if venue in ("raydium_cpmm","raydium_clmm"):
            fee=decode_native_config_fee(venue,item["decoded_pool_state"],fixture)
            if (fee.get("venue")!=venue or
                    fee.get("config_address")!=item["decoded_pool_state"]["amm_config"]):
                raise ValueError("source fee config not bound to decoded pool")
            effective=fee.get("effective_quote_fee_ppm")
            if fee.get("total_effective_fee_authenticated") is True:
                if type(effective) is not int or not 0<=effective<1_000_000:
                    raise ValueError("authenticated effective fee ppm missing")
            elif effective is not None:
                raise ValueError("unverified effective fee cannot be projected")
            if venue=="raydium_cpmm":
                # Legacy synthetic projection tests may omit fee liabilities.
                # Never silently use unadjusted vaults in creator-fee quoting.
                fee_state=item["decoded_pool_state"]
                fee_keys=[f"{name}_token_{i}" for i in (0,1)
                          for name in ("protocol_fees","fund_fees","creator_fees")]
                row["cpmm_effective_reserves_base_units"]=(
                    effective_reserves(fee_state,fundamentals["vault_base_units"])
                    if all(key in fee_state for key in fee_keys) else None)
                row["native_trade_fee_ppm"]=fee.get("trade_fee_ppm")
                row["native_creator_fee_ppm"]=fee.get("creator_fee_ppm")
                row["creator_fee_enabled"]=fee.get("creator_fee_enabled")
                row["creator_fee_on"]=fee.get("creator_fee_on")
            if fee["total_effective_fee_authenticated"] is True:
                row.update(trade_fee_ppm=fee["effective_quote_fee_ppm"],
                           trade_fee_authenticated=True)
                if venue=="raydium_clmm":
                    row.update(liquidity=fundamentals["liquidity"],
                               sqrt_price_x64=fundamentals["sqrt_price_x64"])
                    blocked.append({"venue":venue,"pool":row["address"],
                          "reason":"directional tick array bounds not derived"})
                else:
                    blocked.append({"venue":venue,"pool":row["address"],
                          "reason":"indicative CPMM only; signed output parity unverified"})
            else:
                row["trade_fee_authenticated"]=False
                blocked.append({"venue":venue,"pool":row["address"],
                        "reason":"CPMM creator fee treatment not authenticated"})
        else:
            row["trade_fee_authenticated"]=False
            blocked.append({"venue":venue,"pool":row["address"],
                     "reason":"remaining venue auxiliary pricing required"})
        outputs.append(row)
    return {"status":"PARTIAL_ACCOUNT_DERIVED_QUOTE_STATE",
            "snapshots":outputs,"blocked_or_indicative":blocked,
            "full_seven_venue_pricing_verified":False,**SAFE}

def quote_cpmm_only(fixture,*,observed_unix,leg,amount_in):
    report=derive(fixture,observed_unix=observed_unix)
    state=next((s for s in report["snapshots"]
                if (s["venue"],s["address"])==(leg.get("venue"),leg.get("pool"))),None)
    if state is None or state["venue"]!="raydium_cpmm" or state.get("trade_fee_authenticated") is not True:
        raise ValueError("CPMM source fee/reserves unavailable")
    provider,registry=from_snapshot([state],now=observed_unix)
    quoted=provider(leg,amount_in)
    mints=state["mints"]
    if leg.get("input_mint") not in mints or leg.get("output_mint")!=mints[1-mints.index(leg["input_mint"])]:
        raise ValueError("CPMM quote direction not bound to source pool mints")
    i=mints.index(leg["input_mint"])
    reserves=state["vault_base_units"]
    fee_interval=quote_fee_rounding_interval(reserves[i],reserves[1-i],
        amount_in,state["trade_fee_ppm"])
    candidates=quote_native_fee_candidates(reserves[i],reserves[1-i],
        amount_in,state["trade_fee_ppm"])
    return {"status":"ACCOUNT_DERIVED_CPMM_INDICATIVE_ONLY",
            "native_fee_candidate_quotes":candidates,
            "native_fee_rounding_reference":fee_interval,
            "quote":quoted,"protocol_exact_verified":False,
            "signed_execution_reconciled":False,**SAFE}

def quote_cpmm_creator_fee_source(fixture,*,observed_unix,leg,amount_in):
    """CPMM-only source-bound creator fee diagnostic; remains indicative."""
    report=derive(fixture,observed_unix=observed_unix)
    matching=[s for s in report["snapshots"]
              if s["venue"]=="raydium_cpmm" and s["address"]==leg.get("pool")]
    if len(matching)!=1:raise ValueError("CPMM source pool missing")
    state=matching[0]
    mints=state["mints"]
    if leg.get("input_mint") not in mints:raise ValueError("invalid CPMM input mint")
    idx=mints.index(leg["input_mint"])
    if leg.get("output_mint")!=mints[1-idx]:raise ValueError("invalid CPMM output mint")
    if type(state.get("creator_fee_enabled")) is not bool:
        raise ValueError("CPMM onchain creator fee flag not authenticated")
    reserves=state["cpmm_effective_reserves_base_units"]
    detail=creator_quote(reserves[idx],reserves[1-idx],amount_in,
        state["native_trade_fee_ppm"],state["native_creator_fee_ppm"],
        state["creator_fee_on"],idx,enabled=state["creator_fee_enabled"])
    return {"status":"SOURCE_BOUND_CPMM_CREATOR_FEE_INDICATIVE",
            "quote":{"venue":"raydium_cpmm","pool":leg["pool"],
                "input_mint":leg["input_mint"],"output_mint":leg["output_mint"],
                "amount_in":amount_in,"amount_out":detail["estimated_output_base_units"],
                "snapshot_slot":state["slot"]},
            "venue_fee_detail":detail,"protocol_exact_verified":False,**SAFE}
