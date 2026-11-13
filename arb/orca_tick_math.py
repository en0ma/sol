"""Orca Whirlpool integer tick-index -> sqrt-price X64 reference implementation.

Constants and shift orders transcribed from Orca's on-chain tick_math.rs:
https://github.com/orca-so/whirlpools/blob/main/programs/whirlpool/src/math/tick_math.rs

This is pure deterministic math, not evidence of a verified live pool, swap
rounding accuracy or executable arbitrage.
"""
Q = 1 << 64
MAX_TICK = 443636
MIN_SQRT = 4295048016
MAX_SQRT = 79226673515401279992447579055
POSITIVE = (79232123823359799118286999567, 79236085330515764027303304731, 79244008939048815603706035061, 79259858533276714757314932305, 79291567232598584799939703904, 79355022692464371645785046466, 79482085999252804386437311141, 79736823300114093921829183326, 80248749790819932309965073892, 81282483887344747381513967011, 83390072131320151908154831281, 87770609709833776024991924138, 97234110755111693312479820773, 119332217159966728226237229890, 179736315981702064433883588727, 407748233172238350107850275304, 2098478828474011932436660412517, 55581415166113811149459800483533, 38992368544603139932233054999993551)
NEGATIVE = (18445821805675392311, 18444899583751176498, 18443055278223354162, 18439367220385604838, 18431993317065449817, 18417254355718160513, 18387811781193591352, 18329067761203520168, 18212142134806087854, 17980523815641551639, 17526086738831147013, 16651378430235024244, 15030750278693429944, 12247334978882834399, 8131365268884726200, 3584323654723342297, 696457651847595233, 26294789957452057, 37481735321082)


def sqrt_price_from_tick_index(tick):
    if type(tick) is not int or not -MAX_TICK <= tick <= MAX_TICK:
        raise ValueError("tick index out of bounds")
    if tick >= 0:
        ratio = POSITIVE[0] if tick & 1 else (1 << 96)
        for bit, multiplier in enumerate(POSITIVE[1:], start=1):
            if tick & (1 << bit):
                ratio = (ratio * multiplier) >> 96
        price = ratio >> 32
    else:
        magnitude = -tick
        ratio = NEGATIVE[0] if magnitude & 1 else Q
        for bit, multiplier in enumerate(NEGATIVE[1:], start=1):
            if magnitude & (1 << bit):
                ratio = (ratio * multiplier) >> 64
        price = ratio
    if not MIN_SQRT <= price <= MAX_SQRT:
        raise ValueError("computed Whirlpool price outside protocol bounds")
    return price
