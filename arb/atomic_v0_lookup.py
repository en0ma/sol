"""Strictly isolated v0 lookup-table packing for oversized two-venue transactions.

The lookup table is fabricated ONLY inside an explicitly offline disposable
Surfpool. No source-authentication claim is attached to this ephemeral table,
which stores addresses already present in the signed instruction metas.
"""
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call

ALT_PROGRAM="AddressLookupTab1e1111111111111111111111111"

def eligible_addresses(instructions,payer):
    from solders.pubkey import Pubkey
    seen=set()
    result=[]
    for ix in instructions:
        for meta in ix.accounts:
            key=meta.pubkey
            if key!=payer and not meta.is_signer and key not in seen:
                result.append(key)
                seen.add(key)
    if len(result)>240:
        raise ValueError("lookup table exceeds supported account bound")
    return result

def provision_offline_table(rpc,addresses):
    from solders.keypair import Keypair
    local_rpc_only(rpc)
    import os
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("v0 lookup table requires explicitly offline Surfpool")
    if not addresses or len(addresses)>240 or len(set(addresses))!=len(addresses):
        raise ValueError("invalid offline lookup table entries")
    table=Keypair().pubkey()
    # Solana AddressLookupTableMeta (56 bytes): state enum, deactivation
    # slot u64::MAX, last_extended_slot=0, no authority, padding.
    meta=(1).to_bytes(4,"little")+(2**64-1).to_bytes(8,"little")+bytes(44)
    raw=meta+b"".join(bytes(key) for key in addresses)
    call(rpc,"surfnet_setAccount",[str(table),{
        "lamports":max(1000000,1000000+len(raw)*10000),
        "data":raw.hex(),"owner":ALT_PROGRAM,"executable":False}])
    return table

def sign_v0_offline(rpc,instructions,signer,recent_blockhash):
    from solders.address_lookup_table_account import AddressLookupTableAccount
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction
    local_rpc_only(rpc)
    if len(instructions)!=2:
        raise ValueError("v0 atomic fallback requires exactly two swap instructions")
    addresses=eligible_addresses(instructions,signer.pubkey())
    table=provision_offline_table(rpc,addresses)
    lookup=AddressLookupTableAccount(table,addresses)
    msg=MessageV0.try_compile(signer.pubkey(),instructions,[lookup],recent_blockhash)
    tx=VersionedTransaction(msg,[signer])
    tx.verify_and_hash_message()
    if len(bytes(tx))>1232:
        raise ValueError(f"v0 signed packet still too large: {len(bytes(tx))} > 1232 bytes")
    return tx,lookup

def sign_v0_with_lookup(instructions,signer,recent_blockhash,lookup):
    """Reuse the positive transaction's offline ALT for the rollback control."""
    from solders.message import MessageV0
    from solders.transaction import VersionedTransaction
    msg=MessageV0.try_compile(signer.pubkey(),instructions,[lookup],recent_blockhash)
    tx=VersionedTransaction(msg,[signer])
    tx.verify_and_hash_message()
    if len(bytes(tx))>1232:
        raise ValueError("negative v0 signed packet exceeds 1232-byte limit")
    return tx

def resolved_v0_keys(msg,lookup):
    if len(msg.address_table_lookups)!=1:
        raise ValueError("expected exactly one isolated lookup table")
    item=msg.address_table_lookups[0]
    if item.account_key!=lookup.key:
        raise ValueError("unrecognized v0 lookup table address")
    addresses=lookup.addresses
    if any(idx>=len(addresses) for idx in item.writable_indexes+item.readonly_indexes):
        raise ValueError("v0 lookup index out of bounds")
    return list(msg.account_keys)+[addresses[i] for i in item.writable_indexes]+[
        addresses[i] for i in item.readonly_indexes]

def verify_v0_order(tx,lookup,first,second,intermediate):
    from solders.pubkey import Pubkey
    tx.verify_and_hash_message()
    msg=tx.message
    keys=resolved_v0_keys(msg,lookup)
    programs=[str(keys[ix.program_id_index]) for ix in msg.instructions]
    if programs!=[first,second]:
        raise ValueError("v0 signed swap program order incorrect")
    mid=Pubkey.from_string(intermediate)
    if mid not in keys:
        raise ValueError("v0 intermediate SPL account missing")
    index=keys.index(mid)
    if any(index not in ix.accounts for ix in msg.instructions):
        raise ValueError("v0 intermediate SPL account not shared by both swaps")
    return {"instruction_order_verified":True}
