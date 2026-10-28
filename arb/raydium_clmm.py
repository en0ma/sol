"""Raydium CLMM packed PoolState decoding; discovery-only, no swap claim.

Based on raydium-io/raydium-clmm PoolState repr(C,packed), 1544 bytes.
Uses Solana RPC and vault checks; swap/tick-array execution not supported.
"""
import base64,hashlib
from arb.rpc import call
from arb.orca_whirlpool import b58
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
PROGRAM="CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"
SIZE=1544
DISC=hashlib.sha256(b"account:PoolState").digest()[:8]

def decode(raw):
    if len(raw)!=SIZE or raw[:8]!=DISC:raise ValueError("wrong Raydium CLMM account layout")
    def key(i):return b58(raw[i:i+32])
    state={"amm_config":key(9),"owner":key(41),
           "token_mint_0":key(73),"token_mint_1":key(105),
           "token_vault_0":key(137),"token_vault_1":key(169),
           "observation_key":key(201),
           "mint_decimals_0":raw[233],"mint_decimals_1":raw[234],
           "tick_spacing":int.from_bytes(raw[235:237],"little"),
           "liquidity":int.from_bytes(raw[237:253],"little"),
           "sqrt_price_x64":int.from_bytes(raw[253:269],"little"),
           "tick_current":int.from_bytes(raw[269:273],"little",signed=True),
           "swap_status_bits":raw[389],
           "fee_on":raw[390]}
    if state["fee_on"] not in (0,1,2):
        raise ValueError("unsupported source CLMM fee collection mode")
    if state["swap_status_bits"] & (1<<4):
        raise ValueError("source CLMM pool swap disabled")
    if state["tick_spacing"]<=0 or state["sqrt_price_x64"]<=0:
        raise ValueError("invalid CLMM tick spacing or sqrt price")
    if len({state["token_mint_0"],state["token_mint_1"],state["token_vault_0"],state["token_vault_1"]})!=4:
        raise ValueError("duplicate CLMM token mint/vault")
    return state

def fee_collected_from_input(state,mint_in):
    """Return the exact native fee side from source-captured PoolState.

    FeeOn::FromInput=0, Token0Only=1, Token1Only=2.
    This controls the fee side, not the dynamic fee's effective RATE.
    """
    if (not isinstance(state,dict) or
            state.get("fee_on") not in (0,1,2) or
            mint_in not in (state.get("token_mint_0"),state.get("token_mint_1")) or
            state.get("token_mint_0")==state.get("token_mint_1")):
        raise ValueError("authenticated CLMM pool fee side and input mint required")
    input0=mint_in==state["token_mint_0"]
    return (state["fee_on"]==0 or
            (state["fee_on"]==1 and input0) or
            (state["fee_on"]==2 and not input0))

def fee_collection_source_evidence(state,mint_in):
    on_input=fee_collected_from_input(state,mint_in)
    return {"fee_on_native_enum":state["fee_on"],
            "fee_on_input":on_input,
            "fee_side":"INPUT" if on_input else "OUTPUT",
            "source_pool_fee_side_decoded":True,
            "dynamic_fee_rate_protocol_exact_verified":False,
            "protocol_exact_quote_verified":False,
            "actionable":False,"broadcast":False,"live_execution_approved":False}

def verify(rpc,address,state):
    keys=[address,state["token_vault_0"],state["token_vault_1"]]
    response=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value")
    if not isinstance(values,list) or len(values)!=3:raise ValueError("CLMM accounts missing")
    pool=values[0]
    if not pool or pool["owner"]!=PROGRAM or decode(base64.b64decode(pool["data"][0],validate=True))!=state:
        raise ValueError("CLMM pool mismatched or changed")
    balances=[];authorities=[]
    for i in (0,1):
        acct=values[i+1]
        if not acct or acct["owner"]!=TOKEN_PROGRAM:raise ValueError("unsupported vault token program")
        token=decode_token_account(base64.b64decode(acct["data"][0],validate=True))
        if token["mint"]!=state[f"token_mint_{i}"]:raise ValueError("CLMM vault mint mismatch")
        balances.append(token["amount_base_units"])
        authorities.append(token["authority"])
    if min(balances)<=0 or state["liquidity"]<=0 or authorities[0]!=authorities[1]:
        raise ValueError("CLMM vaults or active liquidity invalid")
    return {"venue":"raydium_clmm","address":address,
            "mints":[state["token_mint_0"],state["token_mint_1"]],
            "vault_base_units":balances,"slot":response.get("context",{}).get("slot"),
            "swap_simulated":False}
