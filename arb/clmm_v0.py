"""Build Solana v0 simulation transaction with pre-existing address lookup table.

Lookup table must already exist on the local fork. No transaction
submission or ALT mutation is performed here.
"""
import base64
from arb.rpc import call
ALT_PROGRAM="AddressLookupTab1e1111111111111111111111111"

def load_table(rpc,address):
    from solders.pubkey import Pubkey
    from solders.address_lookup_table_account import AddressLookupTableAccount
    info=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not info or info.get("owner")!=ALT_PROGRAM:
        raise ValueError("missing address lookup table or wrong owner")
    raw=base64.b64decode(info["data"][0],validate=True)
    if len(raw)<56 or (len(raw)-56)%32 or int.from_bytes(raw[:4],"little")!=1:
        raise ValueError("malformed lookup table")
    # ALT deactivation_slot == u64::MAX means active.
    if int.from_bytes(raw[4:12],"little")!=(1<<64)-1:
        raise ValueError("deactivated lookup table unsupported")
    keys=[Pubkey.from_bytes(raw[i:i+32]) for i in range(56,len(raw),32)]
    if len(keys)>256 or len(set(keys))!=len(keys):
        raise ValueError("invalid lookup table address count")
    return AddressLookupTableAccount(Pubkey.from_string(address),keys)

def build_v0(ixs,payer,signers,blockhash,tables):
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction
    from solders.hash import Hash
    message=MessageV0.try_compile(payer.pubkey(),ixs,tables,Hash.from_string(blockhash))
    tx=VersionedTransaction(message,signers)
    if len(bytes(tx))>1232:
        raise ValueError("v0 transaction exceeds 1232 bytes")
    return tx
