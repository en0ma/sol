"""Authenticate Raydium CLMM AmmConfig fees from the same-slot pool snapshot.

PoolState references AmmConfig at byte offset 9. Classic fee fields follow the
upstream Anchor AmmConfig layout; reject unsupported account versions outright.
No claim of signed swap execution.
"""
import base64,hashlib
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode,SIZE


DISC=hashlib.sha256(b"account:AmmConfig").digest()[:8]


def read(rpc,pool_address):
    pool_reply=call(rpc,"getAccountInfo",[pool_address,{"encoding":"base64","commitment":"confirmed"}])
    pool=pool_reply.get("value")
    if not pool or pool.get("owner")!=PROGRAM:
        raise ValueError("invalid CLMM pool owner")
    raw=base64.b64decode(pool["data"][0],validate=True)
    state=decode(raw)
    config_address=state["amm_config"]
    response=call(rpc,"getMultipleAccounts",[
        [pool_address,config_address],{"encoding":"base64","commitment":"confirmed"}])
    slot=response.get("context",{}).get("slot")
    accounts=response.get("value")
    if type(slot) is not int or not isinstance(accounts,list) or len(accounts)!=2:
        raise ValueError("missing synchronized CLMM fee snapshot")
    pool_again,config=accounts
    if (not pool_again or pool_again.get("owner")!=PROGRAM or
        base64.b64decode(pool_again["data"][0],validate=True)!=raw):
        raise ValueError("CLMM pool changed before fee read")
    if not config or config.get("owner")!=PROGRAM:
        raise ValueError("CLMM fee config owner mismatch")
    data=base64.b64decode(config["data"][0],validate=True)
    # Raydium AmmConfig layout:
    # discriminator 8, bump 1, index u16, owner 32,
    # protocol_fee_rate u32, trade_fee_rate u32, tick_spacing u16.
    if len(data)<53 or data[:8]!=DISC:
        raise ValueError("unsupported CLMM fee config layout")
    tick_spacing=int.from_bytes(data[51:53],"little")
    trade_fee=int.from_bytes(data[47:51],"little")
    if tick_spacing!=state["tick_spacing"] or not 0<=trade_fee<1_000_000:
        raise ValueError("CLMM fee config mismatched or out of range")
    return {"state":state,"pool":pool_address,"slot":slot,
        "amm_config":config_address,"trade_fee_rate_ppm":trade_fee,
        "fee_verified_onchain":True,"swap_simulated":False}
