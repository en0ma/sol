"""Read-only PumpSwap GlobalConfig layout from official pump_amm.json IDL.

GlobalConfig alone is not proof of the effective fee: canonical pools may use
pump_fees dynamic tiers. Never produce an executable quote from this decoder.
"""
import base64
import hashlib
from arb.rpc import call
from arb.pumpswap_pool import PROGRAM
from arb.orca_whirlpool import b58

ADDRESS = "ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"
DISC = hashlib.sha256(b"account:GlobalConfig").digest()[:8]
# IDL: discriminator(8), admin(32), lp_fee(8), protocol_fee(8),
# disable_flags(1), recipients(8*32), creator_fee(8).
MIN_SIZE = 321


def decode(raw):
    if not isinstance(raw, bytes) or len(raw) < MIN_SIZE or raw[:8] != DISC:
        raise ValueError("unsupported PumpSwap GlobalConfig")
    lp = int.from_bytes(raw[40:48], "little")
    protocol = int.from_bytes(raw[48:56], "little")
    creator = int.from_bytes(raw[313:321], "little")
    if any(x > 10000 for x in (lp, protocol, creator)):
        raise ValueError("invalid PumpSwap fee basis points")
    flags = raw[56]
    recipients = [b58(raw[57+32*i:57+32*(i+1)]) for i in range(8)]
    return {"lp_fee_bps": lp, "protocol_fee_bps": protocol,
            "coin_creator_fee_bps": creator, "disable_flags": flags,
            "protocol_fee_recipients": recipients,
            "buy_enabled": not bool(flags & 8),
            "sell_enabled": not bool(flags & 16),
            "effective_fee_verified": False,
            "dynamic_fee_config_required": True}


def fetch(rpc):
    value = call(rpc, "getAccountInfo", [ADDRESS, {
        "encoding": "base64", "commitment": "confirmed"}])
    slot = value.get("context", {}).get("slot")
    account = value.get("value")
    if (type(slot) is not int or slot < 0 or not account
            or account.get("owner") != PROGRAM or account.get("executable")
            or account.get("data", [None, None])[1] != "base64"):
        raise ValueError("missing or invalid PumpSwap fee account")
    info = decode(base64.b64decode(account["data"][0], validate=True))
    return {**info, "slot": slot, "address": ADDRESS}
