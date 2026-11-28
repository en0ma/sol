"""Reconcile PumpSwap V2 emitted event prefixes and recorded SPL transfers.

The fixed prefix follows pump-fun/pump-public-docs idl/pump_amm.json
BuyEvent/SellEvent. Anchor event-CPI tag precedes the event discriminator.
Unknown trailing event extensions are not interpreted. This audits recorded
simulation evidence, not an independent replay or universal fee guarantee.
"""
import base64
import struct
from arb.pumpswap_pool import PROGRAM,decode
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.damm_cpmm_atomic_offline import _decode_base58,_inner_token_transfer
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
TAG=bytes.fromhex("e445a52e51cb9a1d")
BUY=bytes((103,244,82,31,44,245,119,119))
SELL=bytes((62,47,55,10,165,3,220,42))
FIELDS=("timestamp","base_amount","quote_limit","user_base_reserve",
        "user_quote_reserve","pool_base_reserve","pool_quote_reserve",
        "quote_amount","lp_bps","lp_fee","protocol_bps","protocol_fee",
        "quote_with_or_without_lp","user_quote_amount")

def decode_prefix(raw):
    from solders.pubkey import Pubkey
    if not isinstance(raw,bytes) or len(raw)<368 or raw[:8]!=TAG or raw[8:16] not in (BUY,SELL):
        raise ValueError("invalid PumpSwap event CPI prefix")
    out=dict(zip(FIELDS,struct.unpack_from("<q13Q",raw,16)))
    start=16+14*8
    for i,k in enumerate(("pool","user","user_base","user_quote","protocol_recipient",
                          "protocol_recipient_token","coin_creator")):
        out[k]=str(Pubkey.from_bytes(raw[start+i*32:start+(i+1)*32]))
    out["creator_bps"],out["creator_fee"]=struct.unpack_from("<2Q",raw,start+224)
    out["direction"]="BUY" if raw[8:16]==BUY else "SELL"
    return out

def audit_event(fixture,tx,response,keys,accounts,index,amount_in,amount_out):
    from solders.pubkey import Pubkey
    from arb.pumpswap_trade_v2 import ORDER
    import hashlib
    verify(fixture)
    pool=fixture["route_pool_addresses"][index]
    state=decode(base64.b64decode(fixture["accounts"][pool]["data"][0],validate=True))
    buy=fixture["route_mints"][index]==state["quote_mint"]
    if fixture["route_mints"][index+1]!=(state["base_mint"] if buy else state["quote_mint"]):
        raise ValueError("PumpSwap event route mint mismatch")
    ix=tx.message.instructions[index]
    metas=[str(keys[k]) for k in ix.accounts]
    tag=hashlib.sha256(("global:"+("buy_exact_quote_in_v2" if buy else "sell_v2")).encode()).digest()[:8]
    if (str(keys[ix.program_id_index])!=PROGRAM or len(metas)!=len(ORDER)
            or len(ix.data)!=24 or bytes(ix.data[:8])!=tag
            or int.from_bytes(ix.data[8:16],"little")!=amount_in):
        raise ValueError("PumpSwap V2 signed instruction mismatch")
    roles=dict(zip(ORDER,metas))
    user_base=accounts[index+1] if buy else accounts[index]
    user_quote=accounts[index] if buy else accounts[index+1]
    if (roles["pool"]!=pool or roles["user_base_token_account"]!=user_base
            or roles["user_quote_token_account"]!=user_quote
            or roles["pool_base_token_account"]!=state["base_vault"]
            or roles["pool_quote_token_account"]!=state["quote_vault"]):
        raise ValueError("PumpSwap signed account role mismatch")
    groups=[g for g in response["innerInstructions"] if g["index"]==index]
    if len(groups)!=1:
        raise ValueError("PumpSwap event group unavailable")
    events=[]
    transfers=[]
    token=Pubkey.from_string(TOKEN_PROGRAM)
    token_index=keys.index(token) if token in keys else None
    for entry in groups[0]["instructions"]:
        flow=_inner_token_transfer(entry,keys,token_index)
        if flow is not None:
            transfers.append(flow)
        if entry.get("programId")==PROGRAM and isinstance(entry.get("data"),str):
            raw=_decode_base58(entry["data"])
            if raw[:8]==TAG and raw[8:16] in (BUY,SELL):
                if entry.get("accounts")!=[roles["event_authority"]]:
                    raise ValueError("PumpSwap event authority mismatch")
                events.append(decode_prefix(raw))
    if len(events)!=1:
        raise ValueError("missing or ambiguous PumpSwap emitted event")
    event=events[0]
    if (event["pool"]!=pool or event["user"]!=roles["user"]
            or event["user_base"]!=user_base or event["user_quote"]!=user_quote
            or event["direction"]!=("BUY" if buy else "SELL")
            or event["coin_creator"]!=state["coin_creator"]):
        raise ValueError("PumpSwap event identity mismatch")
    reserves=[]
    for vault,mint in ((state["base_vault"],state["base_mint"]),
                       (state["quote_vault"],state["quote_mint"])):
        record=fixture["accounts"][vault]
        if record["owner"]!=TOKEN_PROGRAM or record.get("executable") is not False:
            raise ValueError("PumpSwap source vault owner mismatch")
        decoded=decode_token_account(base64.b64decode(record["data"][0],validate=True))
        if decoded["mint"]!=mint or decoded["authority"]!=pool:
            raise ValueError("PumpSwap source vault identity mismatch")
        reserves.append(decoded["amount_base_units"])
    if reserves!=[event["pool_base_reserve"],event["pool_quote_reserve"]]:
        raise ValueError("PumpSwap emitted and source reserve mismatch")
    def total(src,dst):
        return sum(q for a,b,q in transfers if a==src and b==dst)
    buyback=roles["buyback_fee_recipient"]
    if buy:
        vault_in=total(user_quote,state["quote_vault"])
        external_fee=total(user_quote,buyback)
        if (vault_in+external_fee!=amount_in or event["quote_amount"]!=amount_in
                or event["base_amount"]!=amount_out or total(state["base_vault"],user_base)!=amount_out):
            raise ValueError("PumpSwap buy event/SPL conservation mismatch")
        net=event["user_quote_amount"]
    else:
        external_fee=total(state["quote_vault"],buyback)
        vault_in=total(user_base,state["base_vault"])
        if (vault_in!=amount_in or event["base_amount"]!=amount_in
                or event["user_quote_amount"]!=amount_out or total(state["quote_vault"],user_quote)!=amount_out):
            raise ValueError("PumpSwap sell event/SPL conservation mismatch")
        net=event["quote_amount"]
    fees=[event["lp_fee"],event["protocol_fee"],event["creator_fee"]]
    rates=[event["lp_bps"],event["protocol_bps"],event["creator_bps"]]
    expected=[(net*r+9999)//10000 for r in rates]
    # The audit captures the emitted components separately from actual SPL
    # destinations: retained fee liabilities are not external transfers.
    return {"status":"PUMPSWAP_EVENT_AND_RECORDED_SPL_RECONCILED",
        "direction":event["direction"],"source_reserves":reserves,
        "emitted_fee_bps":rates,"emitted_fee_units":fees,
        "component_ceiling_matches":fees==expected,
        "emitted_quote_curve_basis":net,"external_buyback_transfer":external_fee,
        "vault_input_transfer":vault_in,"actual_input":amount_in,"actual_output":amount_out,
        "event":event,"event_prefix_only":True,"protocol_exact_verified":False,**SAFE}
