"""Enumerate untrusted public index pool addresses; authenticate owners onchain.

The index supplies only untrusted *candidate addresses*. Its symbols, venue
labels, quoted prices and volumes are NEVER trusted or used for graph edges.
The local read-only Solana source fork identifies actual pool program owners;
connected_pool_discovery then redecodes pools and independently checks vaults.
No tokens, quotes, reserves, trading decisions or broadcasts come from index.
"""
import argparse
import json
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from arb.rpc import call, _throttled, RPCError
from arb.onchain_pool_discovery import VENUES
from arb.orca_whirlpool import SOL, USDC

INDEX_ENDPOINT="https://api.dexscreener.com/token-pairs/v1/solana/"
SAFETY={"broadcast":False,"actionable":False,"live_execution_approved":False}


def pick_seeds(pools, max_mints=12):
    if not isinstance(pools,list) or type(max_mints)is not int or not 1<=max_mints<=40:
        raise ValueError("invalid seed inventory")
    frequency=Counter()
    venue_counts=Counter()
    mint_venues={}
    for pool in pools:
        if not isinstance(pool,dict):
            raise ValueError("malformed hint")
        venue=pool.get("venue")
        if venue in VENUES:
            venue_counts[venue]+=1
        mints=pool.get("mints")
        if mints is None:
            continue
        if not isinstance(mints,list) or len(mints)!=2:
            raise ValueError("malformed mint seeds")
        for mint in mints:
            if not isinstance(mint,str) or len(mint)<32:
                raise ValueError("invalid source mint seed")
            frequency[mint]+=1
            if venue in VENUES:
                mint_venues.setdefault(mint,set()).add(venue)
    # Preserve liquid hub anchors and sample tokens found on underserved
    # venues, not just the most common SOL/USDC pools. This only selects
    # UNTRUSTED index searches, never authenticates any returned address.
    anchors=[m for m in (SOL,USDC) if m in frequency]
    def rank(mint):
        venues=mint_venues.get(mint,set())
        deficit=max((20-venue_counts[v] for v in venues),default=0)
        return (-deficit,-len(venues),-frequency[mint],mint)
    rest=sorted((m for m in frequency if m not in anchors),key=rank)
    # Keep room for tokens seen on multiple other venues, since a new
    # PumpSwap counterpart needs real cross-venue graph connectivity rather
    # than another isolated memecoin. This is search prioritization only.
    shared=sorted((m for m in frequency if m not in anchors),
                  key=lambda m:(-len(mint_venues.get(m,())),
                                -frequency[m],m))
    budget=max(0,max_mints-len(anchors))
    underserved_slots=(budget+1)//2
    result=anchors+rest[:underserved_slots]
    for mint in shared+rest[underserved_slots:]:
        if len(result)>=max_mints:
            break
        if mint not in result:
            result.append(mint)
    return result


PUBLIC_TOKEN_FEEDS=(
    "https://api.dexscreener.com/token-profiles/latest/v1",
    "https://api.dexscreener.com/token-boosts/latest/v1",
    "https://api.dexscreener.com/token-boosts/top/v1",
)


def public_solana_token_seeds(*, limit=12, fetch=None):
    """Untrusted public trending addresses, NEVER mint or pool attestation.

    Feeds may contain paid promotions or scams. Only chain-attested program,
    mint, reserve and vault data may enter the canonical pool registry.
    """
    if type(limit)is not int or not 1<=limit<=24:
        raise ValueError("bounded public mint feed limit required")
    from solders.pubkey import Pubkey
    def reader(url):
        request=Request(url,headers={"Accept":"application/json",
                       "User-Agent":"sol-pool-address-discovery/1"})
        with urlopen(request,timeout=8) as response:
            if response.geturl()!=url:
                raise ValueError("public token feed redirect rejected")
            payload=response.read(250001)
            if len(payload)>250000:
                raise ValueError("public token feed exceeds byte limit")
            return json.loads(payload)
    load=fetch or reader
    seeds=[];errors=[];seen=set()
    for url in PUBLIC_TOKEN_FEEDS:
        try:
            rows=load(url)
            if not isinstance(rows,list):
                raise ValueError("public token feed must be list")
            for row in rows[:120]:
                if not isinstance(row,dict) or row.get("chainId")!="solana":
                    continue
                mint=row.get("tokenAddress")
                if (not isinstance(mint,str) or not 32<=len(mint)<=44
                        or mint in seen):
                    continue
                try:
                    Pubkey.from_string(mint)
                except ValueError:
                    continue
                seen.add(mint)
                seeds.append(mint)
                if len(seeds)>=limit:
                    break
        except (HTTPError,URLError,OSError,ValueError,RuntimeError) as exc:
            errors.append({"feed":url,"reason":type(exc).__name__+": "+str(exc)[:120]})
        if len(seeds)>=limit:
            break
    return {"status":"UNTRUSTED_PUBLIC_TOKEN_SEARCH_SEEDS_ONLY",
            "mints":seeds,"errors":errors,**SAFETY}


def index_addresses(mints, *, max_addresses=100, fetch=None, exclude_addresses=()):
    if (not isinstance(mints,list) or not 1<=len(mints)<=40 or
            type(max_addresses)is not int or not 1<=max_addresses<=120):
        raise ValueError("bounded public index request required")
    def public_fetch(mint):
        # Do not allow redirects to become a variable endpoint:
        # only a fixed domain and source-mint path are ever requested.
        request=Request(INDEX_ENDPOINT+mint,
                        headers={"Accept":"application/json",
                                 "User-Agent":"sol-offline-index-candidate-research/1"})
        with urlopen(request, timeout=12) as response:
            if response.geturl()!=INDEX_ENDPOINT+mint:
                raise ValueError("public index redirect rejected")
            raw=response.read(2_000_001)
            if len(raw)>2_000_000:
                raise ValueError("public index response too large")
            return json.loads(raw)
    reader=fetch or public_fetch
    if not isinstance(exclude_addresses,(set,tuple,list)) or any(
            not isinstance(a,str) for a in exclude_addresses):
        raise ValueError("invalid excluded known addresses")
    excluded=set(exclude_addresses)
    from solders.pubkey import Pubkey
    observed={};by_seed={mint:{} for mint in mints};errors=[]
    for mint in mints:
        if not isinstance(mint,str) or not 32<=len(mint)<=44:
            raise ValueError("untrusted invalid mint search")
        try:
            data=reader(mint)
            if not isinstance(data,list):
                raise ValueError("public index result must be list")
            for item in data[:500]:
                if not isinstance(item,dict) or item.get("chainId")!="solana":
                    continue
                address=item.get("pairAddress")
                if (not isinstance(address,str) or not 32<=len(address)<=44
                        or address in excluded):
                    continue
                try:
                    Pubkey.from_string(address)
                except ValueError:
                    continue
                base=item.get("baseToken")
                quote=item.get("quoteToken")
                if not isinstance(base,dict) or not isinstance(quote,dict):
                    continue
                if mint not in (base.get("address"),quote.get("address")):
                    continue
                liquidity=item.get("liquidity")
                volume=item.get("volume")
                # Source-index liquidity merely prioritizes verification.
                # Not a trusted vault balance or eligible quote.
                score=(liquidity.get("usd") if isinstance(liquidity,dict) else 0)
                if (not isinstance(score,(int,float)) or score<0 or
                        not float(score)<float("inf")):
                    score=0
                observed[address]=max(float(score),observed.get(address,0))
                by_seed[mint][address]=max(float(score),by_seed[mint].get(address,0))
        except (HTTPError,URLError,OSError,ValueError,RuntimeError) as exc:
            errors.append({"mint":mint,"reason":type(exc).__name__+": "+str(exc)[:140]})
    # A single global liquidity rank is dominated by SOL/USDC.
    # Round-robin each independent mint search for broader candidate coverage.
    ranked={mint:[a for a,_ in sorted(entries.items(),
            key=lambda x:(-x[1],x[0]))] for mint,entries in by_seed.items()}
    addresses=[];selected=set()
    while len(addresses)<max_addresses and any(ranked.values()):
        made_progress=False
        for mint in mints:
            bucket=ranked[mint]
            while bucket and bucket[0] in selected:
                bucket.pop(0)
            if not bucket:
                continue
            address=bucket.pop(0)
            selected.add(address)
            addresses.append(address)
            made_progress=True
            if len(addresses)>=max_addresses:
                break
        if not made_progress:
            break
    return {"status":"UNTRUSTED_INDEX_ADDRESSES_ONLY",
            "selection_mode":"MINT_STRATIFIED_ROUND_ROBIN",
            "addresses":addresses,
            "candidate_count":len(observed),
            "errors":errors,**SAFETY}


def authenticate_owners(rpc,addresses):
    """Source-read pool ownership in batches, then reverify in refresh()."""
    if not isinstance(addresses,list) or len(addresses)>120:
        raise ValueError("bounded candidate account list required")
    from solders.pubkey import Pubkey
    owner_map={record[0]:venue for venue,record in VENUES.items()}
    candidates=[];rejected=[]
    if len(set(addresses))!=len(addresses):
        raise ValueError("duplicate index address")
    for start in range(0,len(addresses),60):
        chunk=addresses[start:start+60]
        for address in chunk:
            Pubkey.from_string(address)
        # Some upstream RPC plans reject large getMultipleAccounts batches.
        # After the RPC client's bounded 429 retries, split only throttled
        # batches; never retry malformed responses or treat missing accounts
        # as authenticated. Single-account throttling remains a hard failure.
        def fetch_bounded(keys):
            try:
                result=call(rpc,"getMultipleAccounts",
                            [keys,{"encoding":"base64","commitment":"confirmed"}])
            except (HTTPError,RPCError) as exc:
                if not _throttled(exc) or len(keys)==1:
                    raise
                middle=len(keys)//2
                return fetch_bounded(keys[:middle])+fetch_bounded(keys[middle:])
            values=result.get("value") if isinstance(result,dict) else None
            if not isinstance(values,list) or len(values)!=len(keys):
                raise ValueError("source account owner response incomplete")
            return values
        for address,info in zip(chunk,fetch_bounded(chunk)):
            venue=(owner_map.get(info.get("owner"))
                   if isinstance(info,dict) and info.get("executable") is False
                   else None)
            if venue:
                candidates.append({"venue":venue,"address":address})
            else:
                rejected.append({"address":address,"reason":"UNSUPPORTED_OR_UNVERIFIED_POOL_OWNER"})
    return {"status":"SOURCE_ACCOUNT_OWNER_CANDIDATE_ONLY",
            "pools":candidates,"rejections":rejected,**SAFETY}


def balance_candidates(candidates, known, *, limit=80):
    """Reserve read-only owner-verified candidate slots for underserved venues.

    This is only resource allocation; every emitted pool is still an untrusted
    candidate until refresh() rechecks program owner, layout, mints and vaults.
    """
    from collections import Counter, defaultdict
    if (not isinstance(candidates,list) or not isinstance(known,list) or
            type(limit)is not int or not 1<=limit<=120):
        raise ValueError("invalid bounded index balancing")
    counts=Counter(x.get("venue") for x in known if isinstance(x,dict))
    registered={(x.get("venue"),x.get("address")) for x in known if isinstance(x,dict)}
    buckets=defaultdict(list)
    seen=set()
    for row in candidates:
        if not isinstance(row,dict) or row.get("venue") not in VENUES:
            raise ValueError("invalid owner-classified source candidate")
        key=(row["venue"],row.get("address"))
        if key in seen or key in registered:
            continue
        seen.add(key)
        buckets[row["venue"]].append(row)
    selected=[]
    while len(selected)<limit and any(buckets.values()):
        venue=min((v for v in buckets if buckets[v]),key=lambda v:(counts[v],v))
        selected.append(buckets[venue].pop(0))
        counts[venue]+=1
    return selected

def pick_amm_v4_leads(leads, known, *, limit=24):
    """Untrusted Raydium API *addresses* only; source verifies actual owners.

    Prefer mint pairs already present on another venue. A claimed program
    label or mint pair from the API is never accepted as chain evidence.
    """
    if (not isinstance(leads,list) or not isinstance(known,list) or
            type(limit) is not int or not 1<=limit<=32):
        raise ValueError("invalid bounded AMM v4 lead selection")
    known_addresses={x.get("address") for x in known if isinstance(x,dict)}
    selected=[];seen=set()
    for item in sorted(leads,key=lambda x:not x.get("matching_peer_mints",False)
                       if isinstance(x,dict) else True):
        if not isinstance(item,dict):
            continue
        address=item.get("address")
        if (not isinstance(address,str) or not 32<=len(address)<=44 or
                address in seen or address in known_addresses):
            continue
        seen.add(address)
        selected.append(address)
        if len(selected)>=limit:
            break
    return selected


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--output",required=True)
    parser.add_argument("--max-mints",type=int,default=12)
    parser.add_argument("--max-addresses",type=int,default=115)
    parser.add_argument("--max-candidates",type=int,default=80)
    parser.add_argument("--amm-v4-candidates",type=int,default=24)
    parser.add_argument("--public-token-seeds",type=int,default=12)
    args=parser.parse_args()
    from arb.six_venue_pipeline import local_rpc_only
    local_rpc_only(args.rpc)
    hints=json.loads(Path(args.registry).read_text())["pools"]
    seeds=pick_seeds(hints,args.max_mints)
    feed=public_solana_token_seeds(limit=args.public_token_seeds)
    # Keep authenticated historical mint seeds first. External feeds
    # provide search QUERIES only; no pair addresses or prices are trusted.
    for mint in feed["mints"]:
        if mint not in seeds and len(seeds)<40:
            seeds.append(mint)
    inventory=index_addresses(seeds,max_addresses=args.max_addresses,
                              exclude_addresses={h["address"] for h in hints
                                                 if isinstance(h,dict) and isinstance(h.get("address"),str)})
    owners=authenticate_owners(args.rpc,inventory["addresses"])
    # Target scarce AMM v4 source identities with a SECOND independently
    # owner-authenticated path. Never trust Raydium API pool identities.
    supplemental_error=None
    extra=[]
    try:
        from arb.atomic_missing_venue_candidates import discover_amm_v4_candidates
        leads=discover_amm_v4_candidates({"pools":hints},max_pages=5)
        selected=pick_amm_v4_leads(
            leads,hints,limit=args.amm_v4_candidates)
        selected=[a for a in selected if a not in inventory["addresses"]]
        if selected:
            authenticated=authenticate_owners(args.rpc,selected)
            extra=[p for p in authenticated["pools"]
                   if p["venue"]=="raydium_amm_v4"]
    except (ValueError,TypeError,KeyError,OSError,RuntimeError,HTTPError,URLError) as exc:
        supplemental_error=type(exc).__name__+": "+str(exc)[:160]
    owners["pools"].extend(extra)
    owners["amm_v4_source_owner_candidate_count"]=len(extra)
    owners["amm_v4_public_lead_error"]=supplemental_error
    owners["source_owner_classified_pool_count"]=len(owners["pools"])
    # refresh() accepts at most 512 total historical + discovered hints.
    remaining=max(0,512-len(hints))
    owners["pools"]=(balance_candidates(owners["pools"],hints,
                       limit=min(args.max_candidates,remaining)) if remaining else [])
    owners["untrusted_index_candidate_count"]=inventory["candidate_count"]
    owners["untrusted_index_errors"]=inventory["errors"]
    owners["seed_mints"]=seeds
    owners["public_token_seed_feed_errors"]=feed["errors"]
    owners["public_token_seed_count"]=len(feed["mints"])
    Path(args.output).write_text(json.dumps(owners,indent=2)+"\n")
    print(json.dumps({"source_owner_candidates":len(owners["pools"]),
                      "untrusted_index_errors":len(inventory["errors"])},indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
