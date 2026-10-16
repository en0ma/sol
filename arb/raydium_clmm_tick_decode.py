"""Decode initialized Raydium CLMM TickArrayState entries without inventing gaps.

Raydium TickState is 168 bytes, with signed liquidity_net BEFORE unsigned\nliquidity_gross; TickArrayState stores 60 contiguous ticks
starting at offset 44. Results only describe this authenticated array.
"""
from arb.raydium_clmm_ticks import SIZE,DISC

TICK_COUNT=60
TICK_BYTES=168
FIRST_TICK=44

def initialized_ticks(raw,start,spacing):
    if (not isinstance(raw,bytes) or len(raw)!=SIZE or raw[:8]!=DISC or
            type(start)is not int or type(spacing)is not int or spacing<=0 or
            int.from_bytes(raw[40:44],"little",signed=True)!=start):
        raise ValueError("invalid CLMM tick array input")
    result=[]
    for i in range(TICK_COUNT):
        pos=FIRST_TICK+i*TICK_BYTES
        index=int.from_bytes(raw[pos:pos+4],"little",signed=True)
        expected=start+i*spacing
        # Verify even uninitialized tick indexes: a malformed packed layout
        # must never be interpreted as usable liquidity.
        if index!=expected:
            raise ValueError("unexpected CLMM tick-array index layout")
        net=int.from_bytes(raw[pos+4:pos+20],"little",signed=True)
        gross=int.from_bytes(raw[pos+20:pos+36],"little")
        if gross:
            if abs(net)>gross:
                raise ValueError("invalid CLMM initialized tick liquidity")
            result.append({"tick_index":index,"liquidity_net":net,"liquidity_gross":gross})
        elif net:
            raise ValueError("uninitialized tick has nonzero net liquidity")
    return result

def next_boundary(ticks,current,zero_for_one):
    if type(current)is not int or type(zero_for_one)is not bool:
        raise ValueError("invalid CLMM tick direction")
    candidates=[t["tick_index"] for t in ticks
                if (t["tick_index"]<=current if zero_for_one
                    else t["tick_index"]>current)]
    if not candidates:
        raise ValueError("next initialized tick outside authenticated array")
    return max(candidates) if zero_for_one else min(candidates)
