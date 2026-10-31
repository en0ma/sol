"""Read-only, mint-bound Metaplex token metadata for human-readable pool pairs.

Names and symbols are creator-controlled DISPLAY labels, not canonical asset
identities. Graph edges must always join by exact verified mint public keys.
"""
import base64
from arb.rpc import call

PROGRAM = "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s"
MAX_MINTS = 160


def parse_metadata(raw, expected_mint):
    from solders.pubkey import Pubkey
    if not isinstance(raw, bytes) or len(raw)<73:
        raise ValueError("metadata account truncated")
    mint_key = bytes(Pubkey.from_string(expected_mint))
    if raw[33:65] != mint_key:
        raise ValueError("token metadata references different mint")
    at=65
    def string(limit):
        nonlocal at
        if at+4>len(raw):
            raise ValueError("metadata string length truncated")
        n=int.from_bytes(raw[at:at+4],"little")
        at+=4
        if n<1 or n>limit or at+n>len(raw):
            raise ValueError("metadata string exceeds native limit")
        value=raw[at:at+n].decode("utf-8").strip("\x00 ")
        at+=n
        if not value or any(ord(c)<32 for c in value):
            raise ValueError("metadata string invalid")
        return value
    name=string(128)
    symbol=string(48)
    if len(symbol)>20:
        raise ValueError("token symbol exceeds readable limit")
    return {"mint":expected_mint,"name":name,"symbol":symbol,
            "source":"METAPLEX_MINT_BOUND_SELF_DECLARED_DISPLAY_ONLY"}


def fetch_labels(rpc, mints):
    from solders.pubkey import Pubkey
    if (not isinstance(mints,(list,tuple)) or len(mints)>MAX_MINTS or
        any(not isinstance(m,str) for m in mints) or
        len(mints)!=len(set(mints))):
        raise ValueError("bounded unique mint addresses required")
    program=Pubkey.from_string(PROGRAM)
    keys=[]
    for mint in mints:
        token=Pubkey.from_string(mint)
        pda,_=Pubkey.find_program_address(
            [b"metadata",bytes(program),bytes(token)],program)
        keys.append(str(pda))
    result={};failures=[]
    for start in range(0,len(keys),60):
        batch=keys[start:start+60]
        response=call(rpc,"getMultipleAccounts",
                      [batch,{"encoding":"base64","commitment":"confirmed"}])
        rows=response.get("value") if isinstance(response,dict) else None
        if not isinstance(rows,list) or len(rows)!=len(batch):
            raise ValueError("metadata response missing account ordering")
        for index,account in enumerate(rows):
            mint=mints[start+index]
            if account is None:
                failures.append({"mint":mint,"reason":"NO_METADATA"})
                continue
            try:
                if account.get("owner")!=PROGRAM or account.get("executable") is not False:
                    raise ValueError("metadata account owner mismatch")
                encoded=account.get("data")
                if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
                    raise ValueError("metadata encoding invalid")
                raw=base64.b64decode(encoded[0],validate=True)
                result[mint]=parse_metadata(raw,mint)
            except (ValueError,UnicodeError,KeyError,TypeError) as exc:
                failures.append({"mint":mint,"reason":str(exc)[:120]})
    return {"status":"MINT_BOUND_DISPLAY_METADATA_ONLY","labels":result,
            "unresolved":failures,"broadcast":False}
