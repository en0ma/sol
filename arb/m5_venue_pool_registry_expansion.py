"""Extend existing venue-owned pool registries; do not create swap/pricing runners.

Orca and Meteora discovery provide UNTRUSTED addresses. The existing
on-chain registry validator uses each venue's own decoder and vault checks.
No source address becomes a registered pool without successful authentication.
"""
import argparse,json
from pathlib import Path
from arb.pool_registry_batches import refresh_batched
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}

def discover_new(rpc,registry,venue,*,count=6,pages=4,revalidate_registered=False):
    if venue not in ("orca","meteora_damm_v2","raydium_cpmm") or type(count)is not int or not 1<=count<=20:
        raise ValueError("unsupported venue/count")
    existing={r["address"] for r in registry["pools"] if r.get("venue")==venue}
    candidates=[]
    if revalidate_registered:
        # Tracked addresses are identity hints, never historical signed proof.
        # Reauthenticate them against current RPC before fresh signed trials.
        candidates=[{"address":r["address"]} for r in registry["pools"]
                    if r.get("venue")==venue and isinstance(r.get("address"),str)]
    elif venue=="orca":
        from arb.orca_api_discovery import fetch_page,parse_page
        cursor=None;seen_cursors=set()
        for _ in range(pages):
            entries,next_cursor=parse_page(fetch_page(cursor=cursor,size=100,min_tvl=0))
            candidates.extend(entries)
            if not next_cursor:break
            if next_cursor in seen_cursors:raise ValueError("Orca cursor cycle")
            seen_cursors.add(next_cursor);cursor=next_cursor
    elif venue=="raydium_cpmm":
        from arb.raydium_cpmm import api_candidate_addresses
        candidates.extend(api_candidate_addresses(pages=pages,page_size=100))
    else:
        from arb.indexed_pool_discovery import fetch_candidates
        for page in range(1,pages+1):
            candidates.extend(fetch_candidates(venue,page=page,page_size=100))
    unseen=[];seen=set()
    for row in candidates:
        a=row.get("address") if isinstance(row,dict) else None
        if not isinstance(a,str) or not a or (a in existing and not revalidate_registered) or a in seen:continue
        seen.add(a)
        unseen.append({"venue":venue,"address":a})
    # Existing decoder/owner/mint/vault checks; untrusted API output never
    # becomes a registry entry until the source RPC proves it.
    verified=[]
    rejected=[]
    for offset in range(0,len(unseen),100):
        if len(verified)>=count:break
        result=refresh_batched(rpc,unseen[offset:offset+100],batch_size=100)
        rejected.extend(result["rejected"])
        for pool in result["verified_pools"]:
            if venue=="orca":
                # This discovery feeds the adaptive native-price signed gate.
                # Generic on-chain identity validity alone is insufficient.
                from arb.orca_whirlpool import fetch_pool
                try:
                    state=fetch_pool(rpc,pool["address"])
                    if state["tick_spacing"]==state["fee_tier_index_seed"]:
                        raise ValueError("non-adaptive Whirlpool unsupported by native quote")
                    if set((state["token_mint_a"],state["token_mint_b"]))!=set(pool["mints"]):
                        raise ValueError("Whirlpool mint identity changed")
                    # Both swap directions need actual on-chain tick-array accounts.
                    # Do not count a pool as signable merely because its pool bytes decode.
                    from arb.whirlpool_swap import select_tick_arrays
                    from arb.orca_whirlpool import PROGRAM as ORCA_PROGRAM
                    from arb.rpc import call
                    keys=list(dict.fromkeys(
                        select_tick_arrays(pool["address"],state["tick_current_index"],
                                           state["tick_spacing"],True)+
                        select_tick_arrays(pool["address"],state["tick_current_index"],
                                           state["tick_spacing"],False)))
                    snapshot=call(rpc,"getMultipleAccounts",
                        [keys,{"encoding":"base64","commitment":"confirmed"}])
                    accounts=snapshot.get("value")
                    if (type(snapshot.get("context",{}).get("slot")) is not int or
                            not isinstance(accounts,list) or len(accounts)!=len(keys)):
                        raise ValueError("Whirlpool tick-array source snapshot incomplete")
                    missing=[key for key,info in zip(keys,accounts)
                             if not isinstance(info,dict) or info.get("owner")!=ORCA_PROGRAM
                             or info.get("executable") is not False]
                    if missing:
                        raise ValueError("Whirlpool signed-direction tick arrays missing or unauthenticated: "+
                                         ",".join(missing[:3]))
                except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                    rejected.append({"venue":venue,"address":pool["address"],
                        "reason":"ORCA_NATIVE_PRICE_ELIGIBILITY_BLOCKED: "+str(exc)[:150]})
                    continue
            if venue=="meteora_damm_v2":
                # Existing venue-specific source fee decoder must accept the
                # actual on-chain bytes before pool admission for native quote.
                import base64
                from arb.rpc import call
                from arb.meteora_damm_v2_source_fee_decoder import decode_fee_state
                try:
                    info=call(rpc,"getAccountInfo",[pool["address"],
                         {"encoding":"base64","commitment":"confirmed"}])["value"]
                    if not isinstance(info,dict):
                        raise ValueError("source DAMM account missing")
                    decode_fee_state(base64.b64decode(info["data"][0],validate=True))
                except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                    rejected.append({"venue":venue,"address":pool["address"],
                        "reason":"VENUE_FEE_DECODER_UNSUPPORTED: "+str(exc)[:150]})
                    continue
            if venue=="raydium_cpmm":
                from arb.cpmm_config import read_pool_config
                try:
                    config=read_pool_config(rpc,pool)
                    if not config["fee_verified_onchain"] or config["creator_fee_placement_verified"]:
                        raise ValueError("CPMM fee evidence not independently verified")
                    from arb.rpc import call
                    import base64
                    from arb.raydium_cpmm import decode
                    info=call(rpc,"getAccountInfo",[pool["address"],{"encoding":"base64","commitment":"confirmed"}])["value"]
                    if not decode(base64.b64decode(info["data"][0],validate=True))["swap_enabled"]:
                        raise ValueError("CPMM swaps disabled")
                except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                    rejected.append({"venue":venue,"address":pool["address"],
                        "reason":"CPMM_NATIVE_PRICING_ELIGIBILITY_BLOCKED: "+str(exc)[:150]})
                    continue
            verified.append(pool)
    accepted=verified[:count]
    if len({p["address"] for p in accepted})!=len(accepted):
        raise ValueError("duplicate validated venue pool")
    identities=[{"venue":venue,"address":p["address"],"mints":p["mints"]}
                for p in accepted]
    return {"venue":venue,"already_registered_count":len(existing),
            "unseen_candidate_count":len(unseen),
            "new_authenticated_count":len(identities),
            "required_new_count":count,"new_authenticated_pools":identities,
            "rejections":rejected[:100],
            "status":"VENUE_REGISTRY_EXPANSION_READY" if len(identities)==count
                     else "VENUE_REGISTRY_EXPANSION_INCOMPLETE",**SAFE}

def expand(rpc,registry,*,count=6,pages=4,venues=("orca","meteora_damm_v2"),counts=None,revalidate_registered=False):
    if not venues or len(set(venues))!=len(venues) or any(v not in ("orca","meteora_damm_v2","raydium_cpmm") for v in venues):
        raise ValueError("invalid native venue discovery selection")
    counts=counts or {}
    if any(v not in venues or type(n) is not int or not 1<=n<=20 for v,n in counts.items()):
        raise ValueError("invalid venue-specific discovery target")
    reports=[discover_new(rpc,registry,v,count=counts.get(v,count),pages=pages,
                          revalidate_registered=revalidate_registered) for v in venues]
    accepted=[p for report in reports for p in report["new_authenticated_pools"]]
    registered={(p["venue"],p["address"]) for p in registry["pools"]}
    for row in accepted:
        key=(row["venue"],row["address"])
        if key in registered and not revalidate_registered:
            raise ValueError("venue registry duplicate promotion")
        registered.add(key)
    # These are verified identities, NOT execution-eligible registry entries.
    # Only signed price parity promotes an address into the usable registry.
    complete=all(r["new_authenticated_count"]==r["required_new_count"] for r in reports)
    return registry,{"status":"BOTH_VENUES_SIX_NEW_POOLS_AUTHENTICATED"
                             if complete else "POOL_DISCOVERY_INCOMPLETE",
        "venues":reports,"authenticated_candidate_count":len(accepted),
        "registered_additional_pools":0,
        "native_pricing_signed_verified":False,**SAFE}

def promote_signed(registry,candidates,orca_receipt,meteora_receipt,*,raydium_candidates=None,raydium_receipt=None,required=6):
    """Fail-closed discovery -> authenticated identity -> signed parity -> registry.

    A summary boolean or exact counter is never sufficient: each trial must
    include its signed execution proof, exact output and both directions.
    """
    if type(required) is not int or required<1:
        raise ValueError("invalid signed pool admission threshold")
    if raydium_candidates is None or raydium_receipt is None:
        raise ValueError("all three venues require authenticated candidates and signed receipts")
    specifications=[
        ("orca",orca_receipt,"ORCA_NEW_POOLS_SIGNED_VERIFIED",
         "ORCA_NEW_POOL_SIGNED_EXACT",("a_to_b","b_to_a"),
         ("signed_spl_output","official_core_output","local_native_output")),
        ("meteora_damm_v2",meteora_receipt,"METEORA_DAMM_V2_CONFIGURED_POOLS_SIGNED_VERIFIED",
         "METEORA_DAMM_V2_OFFICIAL_SIGNED_EXACT",("a_to_b","b_to_a"),
         ("signed_output","official_output")),
    ]
    if raydium_receipt is not None:
        specifications.append(
            ("raydium_cpmm",raydium_receipt,"RAYDIUM_CPMM_SIGNED_VERIFIED",
             "RAYDIUM_CPMM_SIGNED_NATIVE_EXACT",("0_to_1","1_to_0"),
             ("signed_output","native_output")))
    authenticated={}
    for bundle in (candidates,raydium_candidates or {"pools":[]}):
        if not isinstance(bundle,dict) or not isinstance(bundle.get("pools"),list):
            raise ValueError("authenticated candidate manifest missing")
        for entry in bundle["pools"]:
            if not isinstance(entry,dict) or not isinstance(entry.get("address"),str):
                raise ValueError("malformed authenticated pool candidate")
            key=(entry.get("venue"),entry["address"])
            if key in authenticated:
                raise ValueError("duplicate authenticated pool candidate")
            mints=entry.get("mints")
            if not isinstance(mints,list) or len(mints)!=2 or len(set(mints))!=2:
                raise ValueError("authenticated candidate mint identity required")
            authenticated[key]=entry
    existing={}
    for row in registry["pools"]:
        key=(row["venue"],row["address"])
        if key in existing:raise ValueError("duplicate pool already in tracked registry")
        existing[key]=row
    verified={}
    for venue,receipt,status,trial_status,directions,outputs in specifications:
        if not isinstance(receipt,dict) or receipt.get("status")!=status or not isinstance(receipt.get("pools"),list):
            raise ValueError(venue+" signed verification missing or failed")
        approved=set()
        for pool in receipt["pools"]:
            if not isinstance(pool,dict) or pool.get("verified") is not True:continue
            address=pool.get("pool")
            if not isinstance(address,str) or (venue,address) not in authenticated:
                raise ValueError(venue+" signed pool absent from authenticated discovery")
            trials=pool.get("trials")
            if not isinstance(trials,list) or len(trials)!=4:
                raise ValueError(venue+" requires four signed trials per pool")
            observations={}
            for trial in trials:
                if not isinstance(trial,dict) or trial.get("status")!=trial_status:
                    raise ValueError(venue+" signed trial lacks exact execution proof")
                if trial.get("pool")!=address or trial.get("direction") not in directions:
                    raise ValueError(venue+" signed trial pool/direction identity mismatch")
                # Different venue runners use input or amount_in. If both
                # are supplied they must identify the same signed input.
                if "input" in trial and "amount_in" in trial and (
                        type(trial["input"]) is not int or
                        type(trial["amount_in"]) is not int or
                        trial["input"]!=trial["amount_in"]):
                    raise ValueError(venue+" conflicting signed trial input amounts")
                size=trial.get("input",trial.get("amount_in"))
                if type(size)is not int or size<=0:
                    raise ValueError(venue+" signed trial has invalid input size")
                if not (isinstance(trial.get("signed_sha256"),str) and
                        len(trial["signed_sha256"])==64 and
                        all(ch in "0123456789abcdefABCDEF" for ch in trial["signed_sha256"])) and not (
                        venue=="raydium_cpmm" and isinstance(trial.get("signature"),str)
                        and 64<=len(trial["signature"])<=88 and
                        all(ch in "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
                            for ch in trial["signature"])):
                    raise ValueError(venue+" signed transaction evidence missing")
                values=[trial.get(k) for k in outputs]
                if any(type(v)is not int or v<=0 for v in values) or len(set(values))!=1:
                    raise ValueError(venue+" source-native and signed SPL outputs differ")
                key=(trial["direction"],size)
                if key in observations:
                    raise ValueError(venue+" duplicate signed trial size/direction")
                observations[key]=True
            if any(sum(direction==x[0] for x in observations)!=2 for direction in directions):
                raise ValueError(venue+" both swap directions require two sizes")
            if not any(k in pool for k in ("exact","exact_matches")) or any(
                    type(pool[k]) is not int or pool[k]!=4
                    for k in ("exact","exact_matches") if k in pool):
                raise ValueError(venue+" reported exact count disagrees with evidence")
            if "trial_count" in pool and (type(pool["trial_count"]) is not int or pool["trial_count"]!=4):
                raise ValueError(venue+" reported trial count disagrees with evidence")
            if address in approved:raise ValueError(venue+" duplicate approved signed pool")
            approved.add(address)
        if len(approved)<required:
            raise ValueError(venue+" fewer than required distinct fully signed pools")
        verified[venue]=approved
    fresh=[]
    for (venue,address),row in authenticated.items():
        if address in verified.get(venue,set()):
            old=existing.get((venue,address))
            if old is None:
                fresh.append({"venue":venue,"address":address,"mints":row["mints"]})
            elif "mints" in old and sorted(old["mints"])!=sorted(row["mints"]):
                raise ValueError(venue+" tracked mint identity disagrees with authenticated state")
    for venue,approved in verified.items():
        if len({p["address"] for p in fresh if p["venue"]==venue}|
               {address for v,address in existing if v==venue and address in approved})<required:
            raise ValueError(venue+" incomplete authenticated registry admission")
    return {**registry,"pools":[*registry["pools"],*fresh]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--rpc",default="http://127.0.0.1:8899")
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--count",type=int,default=6)
    p.add_argument("--pages",type=int,default=4)
    p.add_argument("--orca-count",type=int)
    p.add_argument("--revalidate-registered",action="store_true")
    p.add_argument("--venues",default="orca,meteora_damm_v2")
    p.add_argument("--output-registry",required=True)
    p.add_argument("--output-new-pools",required=True)
    p.add_argument("--report",required=True)
    a=p.parse_args()
    registry=json.loads(Path(a.registry).read_text())
    expanded,report=expand(a.rpc,registry,count=a.count,pages=a.pages,
        venues=tuple(a.venues.split(",")),
        counts={"orca":a.orca_count} if a.orca_count is not None else None,
        revalidate_registered=a.revalidate_registered)
    Path(a.output_registry).write_text(json.dumps(expanded,indent=2)+"\n")
    additions=[p for venue in report["venues"] for p in venue["new_authenticated_pools"]]
    Path(a.output_new_pools).write_text(json.dumps({"pools":additions},indent=2)+"\n")
    Path(a.report).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
                      "authenticated_candidate_count":report["authenticated_candidate_count"],
                      "registered_additional_pools":0,**SAFE}))
    if any(v["new_authenticated_count"]!=v["required_new_count"] for v in report["venues"]):
        raise SystemExit("venue-specific authenticated discovery target not met: "+
            json.dumps({v["venue"]:{"accepted":v["new_authenticated_count"],
                                  "required":v["required_new_count"],
                                  "rejections":v["rejections"][:5]}
                        for v in report["venues"] if v["new_authenticated_count"]!=v["required_new_count"]}))

if __name__=="__main__":main()
