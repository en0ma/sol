"""Seven-venue fixture-derived pool liquidity and native fee/price fundamentals.

Reads ONLY manifest-bound classic SPL token vaults and decoded native pool
layouts. Fee configuration accounts, DLMM bin arrays and OpenBook net
reserves require separate account-specific decoders: never infer their data
from the vaults or caller assertions. Not a complete quote-state extractor.
"""
import base64
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.token_vaults import decode_token_account,TOKEN_PROGRAM
SAFETY={"actionable":False,"live_execution_approved":False,"broadcast":False}
VAULTS={
"orca":("token_vault_a","token_vault_b"),
"raydium_cpmm":("token_0_vault","token_1_vault"),
"raydium_clmm":("token_vault_0","token_vault_1"),
"meteora_dlmm":("reserve_x","reserve_y"),
"meteora_damm_v2":("token_a_vault","token_b_vault"),
"pumpswap":("base_vault","quote_vault"),
"raydium_amm_v4":("base_vault","quote_vault")}
def _positive_int(x,label):
    if type(x)is not int or x<=0:raise ValueError("missing positive "+label)
    return x
def extract(fixture):
    decoded=extract_pool_states(fixture)
    accounts=fixture["accounts"]
    included=set(fixture["state_account_addresses"])
    out=[]
    for row in decoded:
        venue=row["venue"];state=row["decoded_pool_state"]
        vaults=[state[x] for x in VAULTS[venue]]
        if len(set(vaults))!=2 or not all(x in included for x in vaults):
            raise ValueError("source vaults missing from contextual account inventory")
        balances=[];authorities=[]
        for address,mint in zip(vaults,row["mints"]):
            info=accounts[address]
            if info.get("owner")!=TOKEN_PROGRAM or info.get("executable") is not False:
                raise ValueError("unauthenticated classic SPL vault")
            encoded=info.get("data")
            if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
                raise ValueError("invalid vault source encoding")
            token=decode_token_account(base64.b64decode(encoded[0],validate=True))
            if token["mint"]!=mint:raise ValueError("source vault mint mismatch")
            balances.append(_positive_int(token["amount_base_units"],"vault reserves"))
            authorities.append(token["authority"])
        if authorities[0]!=authorities[1]:
            raise ValueError("vault authorities differ")
        fundamentals={"venue":venue,"address":row["address"],"mints":row["mints"],
            "vault_base_units":balances,"vault_addresses":vaults,
            "snapshot_slot":row["snapshot_slot"],"source_authenticated":True,
            "effective_trade_fee_authenticated":False,"protocol_exact_quote_verified":False}
        if venue=="orca":
            fundamentals.update(liquidity=_positive_int(int(state["liquidity"]),"Orca liquidity"),
                sqrt_price_x64=_positive_int(int(state["sqrt_price_x64"]),"Orca sqrt price"),
                fee_rate_hundredths_bps=state["fee_rate_hundredths_bps"],
                fee_rate_read_from_native_pool=True)
        elif venue=="raydium_clmm":
            fundamentals.update(liquidity=_positive_int(state["liquidity"],"CLMM liquidity"),
                sqrt_price_x64=_positive_int(state["sqrt_price_x64"],"CLMM price"))
        elif venue=="meteora_damm_v2":
            fundamentals.update(liquidity=_positive_int(state["liquidity"],"DAMM liquidity"),
                sqrt_price_x64=_positive_int(state["sqrt_price"],"DAMM price"))
        elif venue=="meteora_dlmm":
            fundamentals.update(active_id=state["active_id"],bin_step=state["bin_step"],
                active_bin_account_pricing_verified=False)
        elif venue=="pumpswap":
            fundamentals.update(virtual_quote_reserves=state["virtual_quote_reserves"],
                creator_fee_bps=state["creator_fee_bps"],
                effective_fee_from_config_verified=False)
        elif venue=="raydium_amm_v4":
            fundamentals.update(base_need_take_pnl=state["base_need_take_pnl"],
                quote_need_take_pnl=state["quote_need_take_pnl"],
                openbook_adjusted_reserves_verified=False)
        out.append(fundamentals)
    return {"status":"SEVEN_VENUE_FIXTURE_FUNDAMENTALS_EXTRACTED",
            "venues":[x["venue"] for x in out],"fundamentals":out,
            "signed_quote_accuracy_verified":False,
            "full_fee_and_liquidity_account_derivation_verified":False,**SAFETY}
