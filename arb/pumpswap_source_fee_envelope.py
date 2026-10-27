"""Source-bound PumpSwap fee-tier envelope, not an effective-fee guess.

Canonical fee-program PDA, global config and pool vaults must be captured
together. Every applicable rate candidate is assessed; absent authenticated
market cap or fee mode the answer is a bounded research interval only.
"""
from arb.fixture_pool_fundamentals import extract
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.pumpswap_fee_account import authenticated_address,decode_authenticated
from arb.pumpswap_global_config import ADDRESS,decode as global_decode
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_quote import DENOM
from arb.source_snapshot_manifest import verify
import base64
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
def quote_fee_candidates(fixture,*,pool,mint_in,amount_in):
    if type(amount_in)is not int or not 0<amount_in<2**64 or any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("safe integer source amount required")
    verify(fixture)
    rows=extract_pool_states(fixture)
    row=next((r for r in rows if r["venue"]=="pumpswap" and r["address"]==pool),None)
    if row is None:raise ValueError("PumpSwap source pool absent")
    state=row["decoded_pool_state"]
    included=set(fixture["state_account_addresses"])
    fee_address,_=authenticated_address()
    if fee_address not in included or ADDRESS not in included:
        raise ValueError("canonical fee and global config not present in same-slot source manifest")
    if fee_address not in fixture["accounts"] or ADDRESS not in fixture["accounts"]:
        raise ValueError("canonical fee or global account bytes missing")
    fee=decode_authenticated(fixture["accounts"][fee_address],address=fee_address)
    account=fixture["accounts"][ADDRESS]
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("unauthenticated PumpSwap global config")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("untrusted global configuration bytes")
    global_state=global_decode(base64.b64decode(encoded[0],validate=True))
    fundamentals=next((x for x in extract(fixture)["fundamentals"] if x["address"]==pool),None)
    if fundamentals is None:raise ValueError("PumpSwap SPL vault evidence absent")
    base,quote=fundamentals["vault_base_units"]
    accrued=state["protocol_fees"]+state["creator_fees"]
    virtual=state["virtual_quote_reserves"]
    if any(type(x)is not int for x in (base,quote,accrued,virtual)) or min(base,quote)<=0 or accrued<0 or accrued>=quote or virtual<0:
        raise ValueError("invalid source PumpSwap fee liabilities")
    base_mint,quote_mint=state["base_mint"],state["quote_mint"]
    if mint_in not in (base_mint,quote_mint):raise ValueError("PumpSwap input direction mismatch")
    from_base=mint_in==base_mint
    if not global_state["sell_enabled" if from_base else "buy_enabled"]:
        raise ValueError("source PumpSwap direction disabled")
    pricing_quote=quote+virtual
    spent_quote=quote-accrued
    r_in,r_out=(base,pricing_quote) if from_base else (pricing_quote,base)
    candidates=[("global",global_state)]
    for name,fees in (("flat",fee["flat_fees"]),("exotic",fee["exotic_flat_fees"])):
        candidates.append((name,fees))
    for kind,tiers in (("standard",fee["fee_tiers"]),("stable",fee["stable_fee_tiers"])):
        candidates.extend((kind+":"+str(t["market_cap_threshold"]),t["fees"]) for t in tiers)
    outcomes=[]
    for name,fees in candidates:
        values=[fees[k] for k in ("lp_fee_bps","protocol_fee_bps")]+[
            fees.get("creator_fee_bps",fees.get("coin_creator_fee_bps"))]
        if any(type(v)is not int or v<0 for v in values):
            raise ValueError("malformed account-derived PumpSwap fee tier")
        rate=sum(values)*100
        if rate>=DENOM:raise ValueError("PumpSwap fee tier exhausts input")
        net=amount_in*(DENOM-rate)//DENOM
        if not net:continue
        output=r_out*net//(r_in+net)
        if not 0<output<r_out or (from_base and output>spent_quote):continue
        outcomes.append({"tier":name,"total_fee_ppm":rate,"amount_out":output})
    if not outcomes:
        return {"status":"PUMPSWAP_SOURCE_FEE_CANDIDATES_CANNOT_FILL",
                "source_slot":fixture["state_accounts_observed_slot"],
                "effective_fee_verified":False,"protocol_exact_verified":False,**SAFE}
    return {"status":"PUMPSWAP_SOURCE_FEE_TIER_SCENARIOS_NOT_EXHAUSTIVE",
            "source_slot":fixture["state_accounts_observed_slot"],"pool":pool,
            "input_mint":mint_in,"amount_in":amount_in,
            "candidate_count":len(outcomes),"candidates":outcomes,
            "minimum_candidate_output":min(x["amount_out"] for x in outcomes),
            "maximum_candidate_output":max(x["amount_out"] for x in outcomes),
            "all_possible_fee_modes_exhaustively_verified":False,
            "effective_fee_verified":False,"protocol_exact_verified":False,**SAFE}
