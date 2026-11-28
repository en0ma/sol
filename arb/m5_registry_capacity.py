"""Bounded ephemeral registry admission for source-verified pool discoveries.

Pool candidates were authenticated by the caller; this selector ONLY chooses
which of those candidates enter subsequent independent source probing. Mint
labels and marginal topology are scheduling hints, not evidence of swaps.
"""
from arb.m5_start_mint_expansion import topology

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
MAX_REGISTRY_POOLS=768


def admit(existing,candidates,*,maximum=MAX_REGISTRY_POOLS):
    if (not isinstance(existing,list) or not isinstance(candidates,list)
            or (maximum is not None and (type(maximum)is not int
                or not 1<=maximum<=MAX_REGISTRY_POOLS or len(existing)>maximum))):
        raise ValueError("invalid bounded source pool registry")
    seen=set()
    for row in existing:
        key=(row["venue"],row["address"])
        if key in seen:
            raise ValueError("duplicate source pool identity")
        seen.add(key)
    remaining=[]
    for row in candidates:
        if (not isinstance(row,dict) or row.get("source_verified_only") is not True
                or row.get("venue") not in ("raydium_cpmm","raydium_clmm",
                   "meteora_damm_v2","meteora_dlmm","orca","pumpswap",
                   "raydium_amm_v4")
                or not isinstance(row.get("address"),str) or not row["address"]
                or not isinstance(row.get("mints"),list)
                or len(row["mints"])!=2 or
                not all(isinstance(m,str) and m for m in row["mints"])
                or row["mints"][0]==row["mints"][1]
                or type(row.get("source_verified_slot")) is not int
                or row["source_verified_slot"]<0):
            raise ValueError("source-verified candidate identity required")
        key=(row["venue"],row["address"])
        if key in seen:
            continue
        seen.add(key)
        remaining.append(row)
    candidate_count=len(remaining)
    count=candidate_count if maximum is None else min(maximum-len(existing),candidate_count)
    # First retain pools completing NEW three-hop start tokens. With more
    # room than candidates, avoid costly topology recomputation entirely.
    if count==len(remaining):
        chosen=remaining
    else:
        selected=list(existing)
        current=set(topology(selected)["three_hop_start_mints"])
        chosen=[]
        for _ in range(count):
            best=None
            best_score=(-1,-1)
            for i,row in enumerate(remaining):
                starts=set(topology(selected+[row])["three_hop_start_mints"])
                score=(len(starts-current),
                       int(tuple(sorted(row["mints"])) not in {
                           tuple(sorted(p["mints"])) for p in selected}))
                if score>best_score:
                    best,best_score=i,score
            row=remaining.pop(best)
            chosen.append(row)
            selected.append(row)
            current=set(topology(selected)["three_hop_start_mints"])
    return {"admitted":chosen,"admitted_count":len(chosen),
            "unadmitted_count":candidate_count-len(chosen),
            "registry_capacity":maximum,"source_reverification_required":True,
            **SAFE}
