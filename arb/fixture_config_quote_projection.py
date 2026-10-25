"""Account-derived CPMM and CLMM quote-state projection from captured fixtures.

The native pool and vault fundamentals and fee config must share a manifest-
bound captured account inventory. CLMM tick boundaries remain unavailable.
CPMM creator-fee pools cannot be quoted with trade-fee-only economics.
"""
from arb.fixture_pool_fundamentals import extract
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_aux_fee_decoder import decode_native_config_fee
from arb.authenticated_quote_provider import from_snapshot
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def derive(fixture,*,observed_unix):
    if type(observed_unix)is not int or observed_unix<0:
        raise ValueError("valid observed time required")
    pool_states=extract_pool_states(fixture)
    native=extract(fixture)["fundamentals"]
    if len(native)!=2 or len(pool_states)!=2:
        raise ValueError("two source-bound pools required")
    outputs=[];blocked=[]
    for item,fundamentals in zip(pool_states,native):
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
    provider,registry=from_snapshot(report["snapshots"],now=observed_unix)
    quoted=provider(leg,amount_in)
    return {"status":"ACCOUNT_DERIVED_CPMM_INDICATIVE_ONLY",
            "quote":quoted,"protocol_exact_verified":False,
            "signed_execution_reconciled":False,**SAFE}
