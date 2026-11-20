"""Meteora DAMM v2 / DLMM discovery using untrusted official pool indexes.

Official Meteora Data APIs expose paginated GET /pools. Their addresses are
hints only. Mint identity, owner, program layout and vault balances must be
obtained again using the read-only local source-backed fork. Neither indexed
prices nor indexed liquidity enter authenticated graph evidence.
"""
import base64
import json
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from arb.next_ten_fork_pool_probe import PROGRAMS,DECODERS,MINT_KEYS
from arb.onchain_pool_discovery import verify
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.m5_start_mint_expansion import topology

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
HOSTS={
    "meteora_damm_v2":"https://damm-v2.datapi.meteora.ag",
    "meteora_dlmm":"https://dlmm.datapi.meteora.ag",
}


def indexed_addresses(venue,*,pages=2,page_size=100):
    """Retrieve address hints only; reject malformed/partial index pages."""
    if venue not in HOSTS or type(pages)is not int or not 1<=pages<=5 or (
            type(page_size)is not int or not 1<=page_size<=200):
        raise ValueError("invalid Meteora indexer search")
    out=[]
    seen=set()
    for page in range(1,pages+1):
        url=HOSTS[venue]+"/pools?"+urlencode({
            "page":page,"page_size":page_size,"sort_by":"tvl:desc"})
        with urlopen(Request(url,headers={"Accept":"application/json",
                "User-Agent":"sol-source-authenticated-meteora-bridge/1"}),
                timeout=18) as response:
            payload=json.load(response)
        rows=payload.get("data") if isinstance(payload,dict) else None
        if (not isinstance(rows,list) or len(rows)>page_size
                or type(payload.get("current_page")) is not int
                or payload["current_page"]!=page
                or type(payload.get("pages")) is not int
                or payload["pages"]<page):
            raise ValueError("invalid Meteora indexer page")
        for row in rows:
            address=row.get("address") if isinstance(row,dict) else None
            if not isinstance(address,str) or not 32<=len(address)<=44:
                raise ValueError("invalid Meteora pool address hint")
            if address not in seen:
                seen.add(address)
                out.append({"venue":venue,"address":address})
        if len(rows)<page_size or page>=payload["pages"]:
            break
    return out


def discover(rpc,entries,*,venues=("meteora_damm_v2","meteora_dlmm"),
             pages=2,page_size=100,maximum_verify_per_venue=32,
             index_fn=None,call_fn=None,verify_fn=None):
    """Verify bounded indexed pool identities and rank new missing edges."""
    local_rpc_only(rpc)
    if (not isinstance(entries,list) or not isinstance(venues,(list,tuple))
            or not venues or len(set(venues))!=len(venues)
            or any(v not in HOSTS for v in venues)
            or type(pages)is not int or not 1<=pages<=5
            or type(page_size)is not int or not 1<=page_size<=200
            or type(maximum_verify_per_venue)is not int
            or not 1<=maximum_verify_per_venue<=64):
        raise ValueError("invalid bounded Meteora discovery")
    index=index_fn or indexed_addresses
    fetch=call_fn or call
    verifier=verify_fn or verify
    known={(r["venue"],r["address"]) for r in entries}
    base=topology(entries)
    before=set(base["three_hop_start_mints"])
    base_pairs={frozenset(row["mints"]) for row in entries}
    neighbors={mint:set(p) for mint,p in base["mint_neighbors"].items()}
    reports={}
    admitted=[]
    for venue in venues:
        try:
            hints=index(venue,pages=pages,page_size=page_size)
        except (OSError,TimeoutError,ValueError,RuntimeError,TypeError,KeyError) as exc:
            reports[venue]={"status":"INDEXER_UNAVAILABLE",
                "error_class":type(exc).__name__,"indexed_addresses":0,
                "source_accounts_checked":0,"verified_pools":0}
            continue
        if not isinstance(hints,list) or len(hints)>pages*page_size:
            raise ValueError("unbounded Meteora index hints")
        addresses=[]
        seen=set()
        for hint in hints:
            if (not isinstance(hint,dict) or hint.get("venue")!=venue
                    or not isinstance(hint.get("address"),str)
                    or not 32<=len(hint["address"])<=44):
                raise ValueError("invalid Meteora pool address")
            address=hint["address"]
            if address not in seen and (venue,address) not in known:
                addresses.append(address)
            seen.add(address)
        decoded=[]
        invalid=0
        for offset in range(0,len(addresses),100):
            batch=addresses[offset:offset+100]
            result=fetch(rpc,"getMultipleAccounts",[batch,
                {"encoding":"base64","commitment":"confirmed"}])
            accounts=result.get("value") if isinstance(result,dict) else None
            if not isinstance(accounts,list) or len(accounts)!=len(batch):
                raise ValueError("missing Meteora source account snapshot")
            for address,account in zip(batch,accounts):
                if not account:
                    continue
                try:
                    if account.get("owner")!=PROGRAMS[venue] or (
                            account.get("executable") is not False):
                        raise ValueError("Meteora program ownership mismatch")
                    state=DECODERS[venue](
                        base64.b64decode(account["data"][0],validate=True))
                    a,b=(state[key] for key in MINT_KEYS[venue])
                    if (not isinstance(a,str) or not isinstance(b,str)
                            or a==b):
                        raise ValueError("invalid Meteora state mints")
                    decoded.append((address,state,a,b))
                except (ValueError,KeyError,TypeError):
                    invalid+=1
        candidate_pairs={frozenset((a,b)) for _,_,a,b in decoded}
        priorities=[]
        for address,state,a,b in decoded:
            edge={"venue":venue,"address":address,"mints":[a,b]}
            immediate=len(set(topology(entries+[edge])[
                "three_hop_start_mints"])-before)
            potential=set()
            for c in neighbors.get(a,()):
                if c!=b and frozenset((b,c)) in candidate_pairs:
                    potential.update((a,b,c))
            for c in neighbors.get(b,()):
                if c!=a and frozenset((a,c)) in candidate_pairs:
                    potential.update((a,b,c))
            priorities.append((immediate,len(potential-before),
                int(frozenset((a,b)) not in base_pairs),address,state,a,b))
        priorities.sort(key=lambda x:(-x[0],-x[1],-x[2],x[3]))
        successes=0
        failed=0
        for _,_,_,address,state,a,b in priorities[:maximum_verify_per_venue]:
            try:
                verified=verifier(rpc,venue,address,state)
                if (not isinstance(verified,dict)
                        or verified.get("venue")!=venue
                        or verified.get("address")!=address
                        or type(verified.get("slot")) is not int
                        or verified["slot"]<0
                        or sorted(verified.get("mints",[]))!=sorted((a,b))
                        or verified.get("swap_simulated") is not False):
                    raise ValueError("invalid independent Meteora verification")
                admitted.append({"venue":venue,"address":address,
                    "mints":verified["mints"],
                    "source_verified_slot":verified["slot"],
                    "source_verified_only":True})
                successes+=1
            except (ValueError,KeyError,TypeError,RuntimeError,OSError):
                failed+=1
        reports[venue]={"status":"SOURCE_VERIFICATION_COMPLETE",
            "indexed_addresses":len(hints),
            "source_accounts_checked":len(addresses),
            "decoded_pool_candidates":len(decoded),
            "invalid_source_accounts":invalid,
            "source_verification_attempts":min(
                maximum_verify_per_venue,len(priorities)),
            "source_verification_failures":failed,
            "verified_pools":successes}
    after=topology(entries+admitted)
    return {"status":"READ_ONLY_METEORA_INDEXED_SOURCE_SCOUT",
        "venue_reports":reports,
        "source_verified_new_pools":admitted,
        "verified_new_pool_count":len(admitted),
        "additional_topology_start_mints":sorted(
            set(after["three_hop_start_mints"])-before),
        "indexer_is_not_source_evidence":True,
        "signed_simulation_verified":False,**SAFE}
