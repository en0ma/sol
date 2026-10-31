"""Bounded contextual Orca and Raydium CLMM initialized-tick extraction.

Reuse already-implemented full raw array decoders; do NOT invent tick arrays
or promote successful pool decoding into complete swap price coverage.
"""
import base64
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.source_snapshot_manifest import verify
from arb.whirlpool_ticks import decode_fixed_ticks,FIXED_LEN,DISC as ORCA_DISC
from arb.raydium_clmm_tick_decode import initialized_ticks
from arb.raydium_clmm_ticks import SIZE as CLMM_SIZE,DISC as CLMM_DISC
from arb.orca_tick_math import sqrt_price_from_tick_index
from arb.next_ten_fork_pool_probe import PROGRAMS
from arb.orca_whirlpool import b58
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def extract(fixture,*,max_arrays=24):
    verify(fixture)
    if type(max_arrays)is not int or not 1<=max_arrays<=48:
        raise ValueError("invalid contextual array bound")
    rows=extract_pool_states(fixture)
    output=[]
    for row in rows:
        venue=row["venue"]
        if venue not in ("orca","raydium_clmm"):continue
        state=row["decoded_pool_state"]
        tick=state["tick_current_index"] if venue=="orca" else state["tick_current"]
        spacing=state["tick_spacing"]
        captured=[]
        for address in fixture["state_account_addresses"]:
            if address==row["address"]:continue
            acct=fixture["accounts"][address]
            if acct.get("owner")!=PROGRAMS[venue] or acct.get("executable") is not False:continue
            encoded=acct.get("data")
            if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
                raise ValueError("malformed candidate tick array account")
            raw=base64.b64decode(encoded[0],validate=True)
            if venue=="orca":
                if len(raw)!=FIXED_LEN or raw[:8]!=ORCA_DISC:continue
                start=int.from_bytes(raw[8:12],"little",signed=True)
                ticks=decode_fixed_ticks(raw,row["address"],start,spacing)
            else:
                if len(raw)!=CLMM_SIZE or raw[:8]!=CLMM_DISC:continue
                if b58(raw[8:40])!=row["address"]:
                    raise ValueError("CLMM tick array pool identity mismatch")
                start=int.from_bytes(raw[40:44],"little",signed=True)
                ticks=initialized_ticks(raw,start,spacing)
            if start%(spacing*(88 if venue=="orca" else 60))!=0:
                raise ValueError("noncanonical tick-array start")
            captured.append({"address":address,"start_tick":start,"initialized_ticks":ticks})
            if len(captured)>max_arrays:raise ValueError("too many contextual tick arrays")
        if len({c["start_tick"] for c in captured})!=len(captured):
            raise ValueError("duplicate contextual tick-array range")
        ticks=sorted([t for c in captured for t in c["initialized_ticks"]],key=lambda x:x["tick_index"])
        indexed=[{"tick_index":t["tick_index"],"liquidity_net":int(t["liquidity_net"]),
                  "sqrt_price_x64":sqrt_price_from_tick_index(t["tick_index"])} for t in ticks] if venue=="orca" else ticks
        output.append({"venue":venue,"pool":row["address"],"snapshot_slot":row["snapshot_slot"],
           "tick_current":tick,"arrays_decoded":len(captured),"tick_arrays":captured,
           "initialized_ticks":indexed,"full_directional_coverage_verified":False})
    return {"status":"CONTEXTUAL_INITIALIZED_TICKS_DECODED",
            "pools":output,"price_accuracy_verified":False,**SAFE}
