"""Legacy Orca SPL Token Swap v1 pool decoder (324-byte SwapVersion layout).

Read-only. Decoding alone does not establish pool validity or swap execution.
"""
from arb.orca_whirlpool import b58

SIZE=324

def decode(raw):
    if not isinstance(raw,bytes) or len(raw)!=SIZE:
        raise ValueError("invalid Orca Token Swap v1 state length")
    version,initialized,bump=raw[:3]
    if version!=1 or initialized!=1:
        raise ValueError("unsupported or uninitialized Orca Token Swap v1")
    key=lambda offset:b58(raw[offset:offset+32])
    state={
        "version":version,"initialized":True,"bump":bump,
        "token_program_id":key(3),"token_a_vault":key(35),
        "token_b_vault":key(67),"pool_mint":key(99),
        "token_a_mint":key(131),"token_b_mint":key(163),
        "pool_fee_account":key(195),
        "trade_fee_numerator":int.from_bytes(raw[227:235],"little"),
        "trade_fee_denominator":int.from_bytes(raw[235:243],"little"),
        "owner_trade_fee_numerator":int.from_bytes(raw[243:251],"little"),
        "owner_trade_fee_denominator":int.from_bytes(raw[251:259],"little"),
        "owner_withdraw_fee_numerator":int.from_bytes(raw[259:267],"little"),
        "owner_withdraw_fee_denominator":int.from_bytes(raw[267:275],"little"),
        "host_fee_numerator":int.from_bytes(raw[275:283],"little"),
        "host_fee_denominator":int.from_bytes(raw[283:291],"little"),
        "curve_type":raw[291],
        "curve_parameters":raw[292:324],
    }
    from arb.token_vaults import TOKEN_PROGRAM
    if state["token_program_id"]!=TOKEN_PROGRAM:
        raise ValueError("unsupported Orca Token Swap v1 token program")
    if len({state[k] for k in ("token_a_vault","token_b_vault",
                              "pool_mint","token_a_mint","token_b_mint")})!=5:
        raise ValueError("duplicate Orca Token Swap v1 pool accounts")
    for prefix in ("trade_fee","owner_trade_fee","owner_withdraw_fee","host_fee"):
        num=state[prefix+"_numerator"]
        den=state[prefix+"_denominator"]
        if not den or num>den:
            raise ValueError("invalid Orca Token Swap v1 fee ratio")
    if state["curve_type"] not in (0,1,2,3):
        raise ValueError("unsupported Orca Token Swap v1 curve")
    return state
