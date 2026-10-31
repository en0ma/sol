"""Decode genuine Meteora DLMM BinArray liquidity, fail closed on layout.

Layout: discriminator(8), index(i64), version(u8), padding(7),
LB pair(32), 70 fixed Borsh Bin entries (144 bytes each).
Source: Meteora DLMM Codama BinArray/Bin definitions, account LEN 10136.
This is account-backed bin inventory only; no effective fee/executable quote.
"""
import base64
from arb.meteora_dlmm_bin_preflight import (
    BIN_ARRAY_DISC,BIN_ARRAY_SIZE,bin_array_pda
)
from arb.meteora_dlmm import PROGRAM
from arb.orca_whirlpool import b58

BIN_START=56
BIN_SIZE=144
EXPECTED_SIZE=BIN_START+BIN_ARRAY_SIZE*BIN_SIZE
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def decode_bin_array(raw, *, pool, index):
    if type(raw) is not bytes or len(raw)!=EXPECTED_SIZE:
        raise ValueError("DLMM BinArray source bytes not the canonical 10136-byte layout")
    if raw[:8]!=BIN_ARRAY_DISC:
        raise ValueError("DLMM BinArray discriminator mismatch")
    actual=int.from_bytes(raw[8:16],"little",signed=True)
    if type(index)is not int or actual!=index:
        raise ValueError("DLMM BinArray index mismatch")
    if raw[16] not in (0,1,2):
        raise ValueError("unsupported DLMM BinArray version")
    if b58(raw[24:56])!=pool:
        raise ValueError("DLMM BinArray parent pool mismatch")
    bins=[]
    for i in range(BIN_ARRAY_SIZE):
        offset=BIN_START+i*BIN_SIZE
        def number(start,n):
            return int.from_bytes(raw[offset+start:offset+start+n],"little")
        amount_x=number(0,8)
        amount_y=number(8,8)
        price=number(16,16)
        # The remaining 112 bytes encode liquidity supply, rewards,
        # fee-per-token checkpoints, and volume counters. Their values
        # do not modify current spendable bin token amounts.
        liquidity_supply=number(32,16)
        if (amount_x or amount_y) and (price==0 or liquidity_supply==0):
            raise ValueError("DLMM funded bin has zero price or liquidity supply")
        bins.append({"bin_id":index*BIN_ARRAY_SIZE+i,
                     "amount_x":amount_x,"amount_y":amount_y,
                     "price_q64":price,
                     "liquidity_supply":liquidity_supply})
    return {"pool":pool,"array_index":index,"array_version":raw[16],
            "bin_count":BIN_ARRAY_SIZE,"bins":bins,
            "active_bin_fee_verified":False,"protocol_exact_verified":False,**SAFE}

def decode_from_fixture(fixture, *, pool, array_index):
    from arb.source_snapshot_manifest import verify
    verify(fixture)
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe DLMM source fixture")
    pda=bin_array_pda(pool,array_index)
    if pda not in fixture["state_account_addresses"]:
        raise ValueError("canonical DLMM BinArray missing from single-slot state inventory")
    account=fixture["accounts"][pda]
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("DLMM BinArray owner mismatch")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("DLMM BinArray base64 source unavailable")
    raw=base64.b64decode(encoded[0],validate=True)
    result=decode_bin_array(raw,pool=pool,index=array_index)
    return {**result,"source_slot":fixture["state_accounts_observed_slot"],
            "bin_array_pda":pda,"source_account_verified":True,**SAFE}

def directional_bins(decoded_arrays, *, active_id, x_to_y):
    if type(active_id)is not int or type(x_to_y)is not bool:
        raise ValueError("invalid DLMM active bin direction")
    all_bins={}
    for decoded in decoded_arrays:
        if not isinstance(decoded,dict) or decoded.get("source_account_verified") is not True:
            raise ValueError("source-authenticated DLMM arrays required")
        for b in decoded["bins"]:
            if b["bin_id"] in all_bins:
                raise ValueError("overlapping DLMM bin arrays")
            all_bins[b["bin_id"]]=b
    direction=-1 if x_to_y else 1
    selected=[]
    current=active_id
    while current in all_bins and len(selected)<70:
        b=all_bins[current]
        selected.append({k:b[k] for k in ("bin_id","amount_x","amount_y","price_q64")})
        current+=direction
    return {"bins":selected,"dynamic_fee_verified":False,
            "protocol_exact_verified":False,**SAFE}
