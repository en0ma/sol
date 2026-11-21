"""Reauthenticate CLMM tick-array bitmap extension in a FULL synchronized read.

Original Raydium swap_v2 requires the bitmap extension in remaining accounts
when traversal leaves the pool's inline bitmap. No synthetic account is allowed.
A second full account read asserts original bytes did not drift; the second slot
becomes the authoritative complete snapshot, not a falsely merged old slot.
"""
import base64
import hashlib
from solders.pubkey import Pubkey
from arb.raydium_clmm import PROGRAM
from arb.rpc import call

SEED=b"pool_tick_array_bitmap_extension"
LENGTH=8+32+64*14*2
DISC=hashlib.sha256(b"account:TickArrayBitmapExtension").digest()[:8]

def bitmap_pda(pool):
    return str(Pubkey.find_program_address(
        [SEED, bytes(Pubkey.from_string(pool))], Pubkey.from_string(PROGRAM))[0])

def attach_authenticated_bitmap(rpc,pool,tick):
    if (not isinstance(tick,dict) or not isinstance(tick.get("synchronized_non_tick_accounts"),list)
        or len(tick["synchronized_non_tick_accounts"])!=7
        or not isinstance(tick.get("tick_arrays"),list)
        or len(tick["tick_arrays"])<1):
        raise ValueError("incomplete CLMM synchronized tick source")
    originals=[*tick["synchronized_non_tick_accounts"],*tick["tick_arrays"]]
    address=bitmap_pda(pool)
    if address in [r.get("address") for r in originals]:
        raise ValueError("bitmap account duplicates original source")
    keys=[r["address"] for r in originals]+[address]
    response=call(rpc,"getMultipleAccounts",
                  [keys,{"encoding":"base64","commitment":"confirmed",
                         "minContextSlot":tick["tick_array_source_slot"]}])
    slot=response.get("context",{}).get("slot")
    values=response.get("value")
    if (type(slot)is not int or slot<tick["tick_array_source_slot"] or
        not isinstance(values,list) or len(values)!=len(keys)):
        raise ValueError("CLMM bitmap synchronized reread missing")
    for expected,current in zip(originals,values):
        if expected.get("present") is False:
            if current is not None:
                raise ValueError("CLMM tick account appeared across bitmap reread")
            continue
        if (not isinstance(current,dict) or
            current.get("owner")!=expected.get("owner") or
            current.get("lamports")!=expected.get("lamports") or
            current.get("data",[])[0]!=expected.get("account_base64")):
            raise ValueError("CLMM source bytes changed across bitmap reread")
    value=values[-1]
    extension={"address":address,"present":False}
    if value is not None:
        if (value.get("owner")!=PROGRAM or value.get("executable") is not False
            or type(value.get("lamports")) is not int or value["lamports"]<0):
            raise ValueError("CLMM bitmap extension owner or lamports invalid")
        encoded=value.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("CLMM bitmap extension encoding invalid")
        raw=base64.b64decode(encoded[0],validate=True)
        if (len(raw)!=LENGTH or raw[:8]!=DISC or
            raw[8:40]!=bytes(Pubkey.from_string(pool)) or
            base64.b64encode(raw).decode()!=encoded[0]):
            raise ValueError("CLMM bitmap extension original bytes invalid")
        extension={"address":address,"present":True,"owner":PROGRAM,
                   "lamports":value["lamports"],"account_base64":encoded[0],
                   "sha256":hashlib.sha256(raw).hexdigest()}
    return {**tick,"tick_array_source_slot":slot,
            "bitmap_extension":extension,
            "bitmap_extension_synchronized_slot":slot}
