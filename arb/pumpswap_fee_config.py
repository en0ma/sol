"""Strict Borsh FeeConfig parser for pump_fees, from official pump_fees.json IDL.

Does not independently authenticate the account owner/PDA or identify stable,
exotic, or cashback fee modes. Never promote parsed rates to executable quotes.
"""
DISC = bytes((143, 52, 146, 187, 219, 123, 76, 155))
MAX_TIERS = 64


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) < 8+1+32+24+4 or raw[:8] != DISC:
        raise ValueError("invalid Pump FeeConfig discriminator or length")
    pos = 8
    bump = raw[pos]
    pos += 1
    admin = raw[pos:pos+32]
    pos += 32

    def fees():
        nonlocal pos
        if len(raw)-pos < 24:
            raise ValueError("truncated Pump FeeConfig fee rates")
        values=[int.from_bytes(raw[pos+8*i:pos+8*(i+1)], "little") for i in range(3)]
        pos += 24
        if any(v>10000 for v in values) or sum(values)>=10000:
            raise ValueError("invalid Pump FeeConfig rate")
        return dict(zip(("lp_fee_bps","protocol_fee_bps","creator_fee_bps"),values))

    def tiers():
        nonlocal pos
        if len(raw)-pos < 4:
            raise ValueError("missing Pump FeeConfig tier count")
        count=int.from_bytes(raw[pos:pos+4],"little")
        pos += 4
        if count>MAX_TIERS:
            raise ValueError("excessive Pump FeeConfig tier count")
        result=[]
        previous=-1
        for _ in range(count):
            if len(raw)-pos < 16:
                raise ValueError("truncated Pump FeeConfig threshold")
            threshold=int.from_bytes(raw[pos:pos+16],"little")
            pos += 16
            if threshold<=previous:
                raise ValueError("unordered Pump FeeConfig tiers")
            previous=threshold
            result.append({"market_cap_threshold":threshold,"fees":fees()})
        return result
    flat=fees()
    standard=tiers()
    stable=tiers()
    exotic=fees()
    if any(raw[pos:]):
        raise ValueError("unsupported nonzero FeeConfig trailing data")
    return {"bump":bump,"admin_bytes":admin.hex(),
            "flat_fees":flat,"fee_tiers":standard,
            "stable_fee_tiers":stable,"exotic_flat_fees":exotic,
            "account_authenticated":False,"effective_fee_verified":False}
