"""Raydium AMM v4 legacy LiquidityStateV4 pool decoder (752 bytes).

Read-only parser. A decoded pool is NOT an executable swap or verified pool.
Fields follow the legacy Raydium liquidity state layout.
"""
from arb.orca_whirlpool import b58

SIZE=752

def decode(raw):
    if not isinstance(raw,bytes) or len(raw)!=SIZE:
        raise ValueError("invalid Raydium AMM v4 pool account size")
    u64=lambda offset:int.from_bytes(raw[offset:offset+8],"little")
    key=lambda offset:b58(raw[offset:offset+32])
    status=u64(0)
    nonce=u64(8)
    base_decimals=u64(32)
    quote_decimals=u64(40)
    if status not in (1,6,7) or nonce>255 or base_decimals>18 or quote_decimals>18:
        raise ValueError("unsupported Raydium AMM v4 status, nonce or decimals")
    result={
        "status":status,"nonce":nonce,
        "base_decimals":base_decimals,"quote_decimals":quote_decimals,
        "base_vault":key(336),"quote_vault":key(368),
        "base_mint":key(400),"quote_mint":key(432),
        "lp_mint":key(464),"open_orders":key(496),
        "market_id":key(528),"market_program":key(560),
        "target_orders":key(592),"withdraw_queue":key(624),
        "lp_vault":key(656),"owner":key(688),
        "base_need_take_pnl":u64(192),"quote_need_take_pnl":u64(200),
    }
    required=("base_vault","quote_vault","base_mint","quote_mint",
              "open_orders","market_id","market_program","owner")
    if len({result[k] for k in required})!=len(required):
        raise ValueError("duplicate Raydium AMM v4 critical accounts")
    return result
