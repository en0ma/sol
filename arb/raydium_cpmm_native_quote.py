"""Raydium CPMM swap-base-input integer quote from a synchronized RPC snapshot.

Mirrors the official cp-swap fee denominator, input/output creator fee mode,
accrued-fee exclusions and constant-product floor arithmetic. Only classic
SPL Token pools; no price API, guessed tiers, token symbols or writes.
A computed source quote is NOT independent signed swap/CPI parity.
"""
import base64
import hashlib
from arb.rpc import call
from arb.raydium_cpmm import PROGRAM, decode
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

CONFIG_DISC=hashlib.sha256(b"account:AmmConfig").digest()[:8]
CONFIG_LEN=236
FEE_DENOM=1000000
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def decode_amm_config(raw):
    if type(raw)is not bytes or len(raw)!=CONFIG_LEN or raw[:8]!=CONFIG_DISC:
        raise ValueError("Raydium authenticated AmmConfig discriminator/size mismatch")
    fields={"trade_fee_rate":int.from_bytes(raw[12:20],"little"),
            "protocol_fee_rate":int.from_bytes(raw[20:28],"little"),
            "fund_fee_rate":int.from_bytes(raw[28:36],"little"),
            "creator_fee_rate":int.from_bytes(raw[108:116],"little")}
    if (fields["trade_fee_rate"]>=FEE_DENOM or
        fields["creator_fee_rate"]>=FEE_DENOM or
        fields["trade_fee_rate"]+fields["creator_fee_rate"]>=FEE_DENOM or
        fields["protocol_fee_rate"]+fields["fund_fee_rate"]>FEE_DENOM):
        raise ValueError("Raydium config fee rates out of bounds")
    return fields

def quote_cpmm_exact_input(rpc,pool,mint_in,amount_in):
    """Read pool, two SPL vaults, and config from the SAME confirmed RPC batch."""
    if (not isinstance(pool,str) or not 32<=len(pool)<=44 or
        not isinstance(mint_in,str) or not 32<=len(mint_in)<=44 or
        type(amount_in)is not int or not 0<amount_in<2**64):
        raise ValueError("CPMM exact-input arguments invalid")
    pool_info=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])
    info=pool_info.get("value") if isinstance(pool_info,dict) else None
    if not isinstance(info,dict) or info.get("owner")!=PROGRAM or info.get("executable"):
        raise ValueError("CPMM pool missing or wrong owner")
    if info.get("data",[None,None])[1]!="base64":
        raise ValueError("CPMM pool encoding unavailable")
    state=decode(base64.b64decode(info["data"][0],validate=True))
    if (state["swap_enabled"] is not True or
        state["token_0_program"]!=TOKEN_PROGRAM or
        state["token_1_program"]!=TOKEN_PROGRAM or
        mint_in not in (state["token_0_mint"],state["token_1_mint"])):
        raise ValueError("CPMM swap disabled or unsupported mint")
    addresses=[pool,state["token_0_vault"],state["token_1_vault"],state["amm_config"]]
    response=call(rpc,"getMultipleAccounts",[addresses,{
        "encoding":"base64","commitment":"confirmed"}])
    accounts=response.get("value") if isinstance(response,dict) else None
    slot=response.get("context",{}).get("slot") if isinstance(response,dict) else None
    if type(slot)is not int or slot<0 or not isinstance(accounts,list) or len(accounts)!=4:
        raise ValueError("incomplete synchronized CPMM source accounts")
    if any(not isinstance(a,dict) or a.get("executable") is not False or
           a.get("data",[None,None])[1]!="base64" for a in accounts):
        raise ValueError("incomplete CPMM account owner/encoding evidence")
    if (accounts[0]["owner"]!=PROGRAM or accounts[3]["owner"]!=PROGRAM or
        accounts[1]["owner"]!=TOKEN_PROGRAM or accounts[2]["owner"]!=TOKEN_PROGRAM):
        raise ValueError("CPMM source account owner mismatch")
    raw_pool=base64.b64decode(accounts[0]["data"][0],validate=True)
    if decode(raw_pool)!=state:
        raise ValueError("CPMM pool changed between discovery and snapshot")
    config=decode_amm_config(base64.b64decode(accounts[3]["data"][0],validate=True))
    vaults=[decode_token_account(base64.b64decode(a["data"][0],validate=True))
            for a in accounts[1:3]]
    if (vaults[0]["mint"]!=state["token_0_mint"] or
        vaults[1]["mint"]!=state["token_1_mint"] or
        vaults[0]["authority"]!=vaults[1]["authority"] or
        min(v["amount_base_units"] for v in vaults)<=0):
        raise ValueError("CPMM vault mint, balance or authority invalid")
    reserves=[]
    for i in (0,1):
        accrued=sum(state[k+f"_token_{i}"] for k in
                    ("protocol_fees","fund_fees","creator_fees"))
        available=vaults[i]["amount_base_units"]-accrued
        if available<=0:
            raise ValueError("CPMM accrued fees exhaust reserves")
        reserves.append(available)
    zero_for_one=mint_in==state["token_0_mint"]
    i=0 if zero_for_one else 1
    other=1-i
    trade_rate=config["trade_fee_rate"]
    creator_rate=config["creator_fee_rate"] if state["enable_creator_fee"] else 0
    creator_mode=state["creator_fee_on"]
    creator_on_input=creator_mode==0 or (creator_mode==1 and zero_for_one) or (
        creator_mode==2 and not zero_for_one)
    total_rate=trade_rate+(creator_rate if creator_on_input else 0)
    total_fee=(amount_in*total_rate+FEE_DENOM-1)//FEE_DENOM
    net_input=amount_in-total_fee
    if net_input<=0:raise ValueError("CPMM trade fully consumed by fees")
    trade_fee=(total_fee if not creator_on_input else
               total_fee-((total_fee*creator_rate)//total_rate if total_rate else 0))
    curve_output=(net_input*reserves[other])//(reserves[i]+net_input)
    creator_fee_output=((curve_output*creator_rate+FEE_DENOM-1)//FEE_DENOM
                        if not creator_on_input else 0)
    output=curve_output-creator_fee_output
    if not 0<output<2**64 or output>=reserves[other]:
        raise ValueError("CPMM quote output exhausted or overflows reserves")
    return {"status":"CPMM_ONCHAIN_INTEGER_NATIVE_QUOTE_SIGNED_PARITY_PENDING",
            "venue":"raydium_cpmm","pool":pool,
            "input_mint":mint_in,"output_mint":state[f"token_{other}_mint"],
            "amount_in_base_units":amount_in,
            "amount_out_base_units":output,
            "swap_fee_input_base_units":trade_fee,
            "creator_fee_output_base_units":creator_fee_output,
            "source_slot":slot,
            "source_account_sha256":[hashlib.sha256(base64.b64decode(a["data"][0],validate=True)).hexdigest()
                                     for a in accounts],
            "reserves_after_accrued_fees_base_units":reserves,
            "fee_config_from_same_slot":True,
            "signed_native_parity_verified":False,
            "independent_rpc_origin_verified":False,
            "net_profitability_verified":False,**SAFE}
