"""Read-only Surfpool token-account evidence for Orca SwapV2 preflight.

Only accepts explicitly local HTTP RPC; this module never signs or broadcasts.
Signer control must be proven separately, not inferred from account ownership.
"""
import base64
import ipaddress
from urllib.parse import urlsplit
from arb.rpc import call

TOKEN_PROGRAMS=frozenset((
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
))

def require_loopback_rpc(url):
    parsed=urlsplit(url)
    if parsed.scheme!="http" or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Surfpool verification requires loopback HTTP RPC")
    try:
        if not ipaddress.ip_address(parsed.hostname).is_loopback:
            raise ValueError("non-loopback RPC forbidden")
    except (ValueError,TypeError) as exc:
        raise ValueError("Surfpool verification requires numeric loopback host") from exc
    return url

def observe_token_account(rpc,address,expected_mint,expected_authority,
                          expected_program,min_context_slot=None):
    require_loopback_rpc(rpc)
    if expected_program not in TOKEN_PROGRAMS:
        raise ValueError("unsupported token program")
    options={"encoding":"base64","commitment":"confirmed"}
    if min_context_slot is not None:
        if type(min_context_slot) is not int or min_context_slot<0:
            raise ValueError("invalid minimum slot")
        options["minContextSlot"]=min_context_slot
    response=call(rpc,"getAccountInfo",[address,options])
    slot=response.get("context",{}).get("slot") if isinstance(response,dict) else None
    info=response.get("value") if isinstance(response,dict) else None
    if type(slot) is not int or not isinstance(info,dict) or info.get("owner")!=expected_program:
        raise ValueError("missing or incorrectly owned local token account")
    encoded=info.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("unexpected token account encoding")
    raw=base64.b64decode(encoded[0],validate=True)
    if len(raw)<165:
        raise ValueError("short SPL token account")
    from solders.pubkey import Pubkey
    mint=str(Pubkey.from_bytes(raw[:32]))
    authority=str(Pubkey.from_bytes(raw[32:64]))
    if mint!=expected_mint or authority!=expected_authority or raw[108]!=1:
        raise ValueError("local token mint, authority, or initialization mismatch")
    return {"account":address,"mint":mint,"authority":authority,
            "token_program":expected_program,"slot":slot,
            "initialized":True,"local_rpc_verified":True,
            "signer_control_verified":False,"actionable":False,
            "executable_quote":False,"broadcast":False}
