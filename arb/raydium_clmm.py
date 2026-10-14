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
           "tick_current":int.from_bytes(raw[269:273],"little",signed=True)}
    if state["tick_spacing"]<=0 or state["sqrt_price_x64"]<=0:
        raise ValueError("invalid CLMM tick spacing or sqrt price")
    if len({state["token_mint_0"],state["token_mint_1"],state["token_vault_0"],state["token_vault_1"]})!=4:
        raise ValueError("duplicate CLMM token mint/vault")
    return state

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
