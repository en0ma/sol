"""Compute source-mint net SOL economics from actual signed local-fork results.

Transaction fee remains a signed-message RPC estimate, not a paid mainnet fee.
Only wrapped native SOL starting mint admits a direct lamport conversion. SPL
start-mint costs require an independently authenticated conversion quote.
"""
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
WSOL="So11111111111111111111111111111111111111112"

def signed_net_economics(receipt, *, start_mint, source_slot):
    if not isinstance(receipt,dict) or any(receipt.get(k)is not False for k in SAFE):
        raise ValueError("safe genuine signed simulation receipt required")
    if (type(start_mint)is not str or
            type(source_slot)is not int or source_slot<0 or
            receipt.get("state_accounts_observed_slot")!=source_slot):
        raise ValueError("signed receipt source identity mismatch")
    amounts=receipt.get("planned_inputs")
    after=receipt.get("positive_post_balances_base_units")
    if (not isinstance(amounts,list) or not amounts or
            type(amounts[0])is not int or amounts[0]<=0 or
            not isinstance(after,list) or len(after)!=len(amounts)+1 or
            any(type(v)is not int or v<0 for v in after)):
        raise ValueError("actual signed token accounting missing")
    gross=after[-1]-amounts[0]
    fee=receipt.get("signed_message_fee_estimate")
    cost=None
    reason="starting mint is not authenticated wrapped SOL; conversion remains unavailable"
    if (start_mint==WSOL and
            isinstance(fee,dict) and
            all(fee.get(k)is False for k in SAFE) and
            fee.get("status")=="SIGNED_MESSAGE_FEE_ESTIMATE_ONLY" and
            fee.get("fee_payer_asset")=="SOL" and
            type(fee.get("estimated_fee_lamports"))is int and
            fee["estimated_fee_lamports"]>=0):
        cost=fee["estimated_fee_lamports"]
        reason="estimated fee priced natively in wrapped SOL; not a fee-paid or profitability receipt"
    return {"status":"SIGNED_LOCAL_SIMULATION_ESTIMATED_NET_NOT_PROFIT_VERIFIED"
                      if cost is not None else "SIGNED_LOCAL_SIMULATION_START_MINT_COST_UNCONVERTED",
            "start_mint":start_mint,"source_slot":source_slot,
            "observed_local_fork_gross_delta_start_mint_base_units":gross,
            "estimated_cost_start_mint_base_units":cost,
            "estimated_net_delta_start_mint_base_units":gross-cost if cost is not None else None,
            "cost_reason":reason,
            "signed_local_simulation_succeeded":receipt.get("signed_atomic_simulation_verified") is True,
            "paid_network_fee_verified":False,"net_profit_verified":False,
            "protocol_exact_quote_verified":False,**SAFE}
