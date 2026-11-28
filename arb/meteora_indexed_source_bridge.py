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


SORT_ORDERS=("tvl:desc",)
ALLOWED_SORT_ORDERS=frozenset(("tvl:desc","volume_24h:desc","pool_created_at:desc"))


def indexed_addresses(venue,*,pages=4,page_size=100,
                      sort_orders=("tvl:desc",)):
    """Untrusted addresses; stable order and global dedup across index sorts.

    Each sort can explore a different population of pools. A malformed
    page fails closed rather than silently asserting a complete search.
    """
    if (venue not in HOSTS or type(pages)is not int or not 1<=pages<=20
            or type(page_size)is not int or not 1<=page_size<=200
            or not isinstance(sort_orders,(tuple,list))
            or not 1<=len(sort_orders)<=3
            or len(set(sort_orders))!=len(sort_orders)
            or any(order not in ALLOWED_SORT_ORDERS for order in sort_orders)
            or pages*len(sort_orders)>60):
        raise ValueError("invalid bounded Meteora indexer search")
    out=[]
    seen=set()
    for order in sort_orders:
        for page in range(1,pages+1):
            url=HOSTS[venue]+"/pools?"+urlencode({
                "page":page,"page_size":page_size,"sort_by":order})
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
             pages=4,page_size=100,maximum_verify_per_venue=48,
             sort_orders=SORT_ORDERS,
             index_fn=None,call_fn=None,verify_fn=None):
    """Verify bounded indexed pool identities and rank new missing edges."""
    local_rpc_only(rpc)
    if (not isinstance(entries,list) or not isinstance(venues,(list,tuple))
            or not venues or len(set(venues))!=len(venues)
            or any(v not in HOSTS for v in venues)
            or type(pages)is not int or not 1<=pages<=20
            or type(page_size)is not int or not 1<=page_size<=200
            or (maximum_verify_per_venue is not None and
                (type(maximum_verify_per_venue)is not int or not 1<=maximum_verify_per_venue<=64))
            or not isinstance(sort_orders,(tuple,list))
            or not 1<=len(sort_orders)<=3
            or len(set(sort_orders))!=len(sort_orders)
            or any(order not in ALLOWED_SORT_ORDERS for order in sort_orders)
            or pages*len(sort_orders)>60):
        raise ValueError("invalid bounded Meteora discovery")
    # Preserve the historical bounded scout contract. The active primary
    # discovery explicitly opts out of pool-count limits with None.
    if maximum_verify_per_venue is not None and (
            pages>5 or pages*len(sort_orders)>8):
        raise ValueError("invalid bounded Meteora discovery")
    index=index_fn or indexed_addresses
    fetch=call_fn or call
    verifier=verify_fn or verify
    known={(r["venue"],r["address"]) for r in entries}
    base=topology(entries)
    before=set(base["three_hop_start_mints"])
    reports={}
    admitted=[]
    for venue in venues:
        try:
            hints=index(venue,pages=pages,page_size=page_size,
                        sort_orders=sort_orders)
        except (OSError,TimeoutError,ValueError,RuntimeError,TypeError,KeyError) as exc:
            reports[venue]={"status":"INDEXER_UNAVAILABLE",
                "error_class":type(exc).__name__,"indexed_addresses":0,
                "source_accounts_checked":0,"verified_pools":0}
            continue
        if not isinstance(hints,list) or len(hints)>pages*page_size*len(sort_orders):
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
        # Re-evaluate each venue against previously SOURCE-verified Meteora
        # additions, not only the original registry. A second venue may
        # complete a triangle opened by the first venue's verified pools.
        current_entries=entries+admitted
        current_graph=topology(current_entries)
        current_starts=set(current_graph["three_hop_start_mints"])
        current_pairs={frozenset(row["mints"]) for row in current_entries}
        neighbors={mint:set(p) for mint,p in current_graph["mint_neighbors"].items()}
        candidate_pairs={frozenset((a,b)) for _,_,a,b in decoded}
        priorities=[]
        for address,state,a,b in decoded:
            common=neighbors.get(a,set())&neighbors.get(b,set())
            immediate=len(({a,b}|common)-current_starts) if common else 0
            potential=set()
            for c in neighbors.get(a,()):
                if c!=b and frozenset((b,c)) in candidate_pairs:
                    potential.update((a,b,c))
            for c in neighbors.get(b,()):
                if c!=a and frozenset((a,c)) in candidate_pairs:
                    potential.update((a,b,c))
            priorities.append((immediate,len(potential-current_starts),
                int(frozenset((a,b)) not in current_pairs),address,state,a,b))
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
            "index_sort_orders":list(sort_orders),
            "index_max_requested_addresses":pages*page_size*len(sort_orders),
            "source_accounts_checked":len(addresses),
            "decoded_pool_candidates":len(decoded),
            "invalid_source_accounts":invalid,
            "source_verification_attempts":len(priorities[:maximum_verify_per_venue]),
            "source_verification_pool_limit":maximum_verify_per_venue,
            "unattempted_decoded_pool_count":len(priorities)-len(priorities[:maximum_verify_per_venue]),
            "requested_index_pages_per_sort":pages,
            "source_verification_failures":failed,
            "verified_pools":successes,
            "ranking_prior_verified_venue_pools":len(current_entries)-len(entries),
            "selection_policy":"NEW_STARTS_THEN_COMPLEMENTARY_MISSING_EDGES_THEN_NEW_PAIR"}
    after=topology(entries+admitted)
    return {"status":"READ_ONLY_METEORA_INDEXED_SOURCE_SCOUT",
        "venue_reports":reports,
        "source_verified_new_pools":admitted,
        "verified_new_pool_count":len(admitted),
        "additional_topology_start_mints":sorted(
            set(after["three_hop_start_mints"])-before),
        "indexer_is_not_source_evidence":True,
        "signed_simulation_verified":False,**SAFE}


def audit_recent_pools_isolated(rpc,baseline_entries,*,pages=2,
                                page_size=100,maximum_verify_per_venue=24,
                                sort_orders=("pool_created_at:desc","volume_24h:desc"),
                                discover_fn=None,snapshot_fn=None,
                                isolated_source_prepare_fn=None):
    """Read-only experiment; never returns pool rows for production admission.

    Existing source-backed, high-TVL authenticated pools are the control
    group. Recent-pool discovery may report incremental authenticated
    topology, but is NOT allowed to displace the control graph or raise
    signed-verification counts. A later controlled CI run must independently
    establish improved signed simulation coverage before promotion.
    """
    if (not isinstance(baseline_entries,list)
            or type(pages) is not int or not 1<=pages<=3
            or type(page_size) is not int or not 1<=page_size<=100
            or type(maximum_verify_per_venue) is not int
            or not 1<=maximum_verify_per_venue<=32
            or not isinstance(sort_orders,(tuple,list))
            or not 1<=len(sort_orders)<=2
            or len(set(sort_orders))!=len(sort_orders)
            or any(order not in ("pool_created_at:desc","volume_24h:desc")
                   for order in sort_orders)
            or pages*len(sort_orders)>6):
        raise ValueError("invalid bounded isolated Meteora audit")
    baseline=topology(baseline_entries)
    scout=discover_fn or discover
    evidence=scout(rpc,list(baseline_entries),pages=pages,
                   page_size=page_size,
                   maximum_verify_per_venue=maximum_verify_per_venue,
                   sort_orders=sort_orders)
    if (not isinstance(evidence,dict)
            or evidence.get("status")!="READ_ONLY_METEORA_INDEXED_SOURCE_SCOUT"
            or not isinstance(evidence.get("source_verified_new_pools"),list)
            or evidence.get("signed_simulation_verified") is not False
            or evidence.get("actionable") is not False
            or evidence.get("broadcast") is not False):
        raise ValueError("invalid isolated recent-pool evidence")
    # Never pass these candidates to the primary registry. Independently
    # re-read each candidate through the SAME read-only source snapshot
    # adapter used by graph preparation; merely authenticated vaults
    # are insufficient to establish source-probe eligibility.
    from arb.next_ten_fork_pool_probe import snapshot
    read=snapshot_fn or snapshot
    before=set(baseline["three_hop_start_mints"])
    source_probed=[]
    rejected=0
    for candidate in evidence["source_verified_new_pools"]:
        if (not isinstance(candidate,dict)
                or candidate.get("source_verified_only") is not True
                or candidate.get("venue") not in HOSTS
                or not isinstance(candidate.get("address"),str)
                or not isinstance(candidate.get("mints"),list)
                or len(candidate["mints"])!=2
                or type(candidate.get("source_verified_slot")) is not int
                or candidate["source_verified_slot"]<0):
            raise ValueError("isolated audit received unauthenticated candidate")
        try:
            probed=read(rpc,candidate["address"],candidate["venue"])
            if (not isinstance(probed,dict)
                    or probed.get("authenticated") is not True
                    or probed.get("venue")!=candidate["venue"]
                    or probed.get("pool")!=candidate["address"]
                    or sorted(probed.get("mints",[]))!=sorted(candidate["mints"])
                    or type(probed.get("slot")) is not int
                    or probed["slot"]<0):
                raise ValueError("independent source probe does not match")
            source_probed.append(candidate)
        except (ValueError,KeyError,TypeError,RuntimeError,OSError):
            rejected+=1
    # Distinct starts that survive the EXTRA source pool probe remain
    # hypotheses only. Never claim a signed capture or atomic simulation.
    later=topology(baseline_entries+source_probed)
    all_later=topology(baseline_entries+evidence["source_verified_new_pools"])
    # Optional isolated source capture receives only candidates that passed
    # the SECOND source snapshot. It must write to a separate directory; no
    # candidate pool identity is returned by this audit.
    isolated_capture={"status":"NOT_REQUESTED","selected_routes":0,
                      "captured_routes":0}
    if isolated_source_prepare_fn is not None:
        if not callable(isolated_source_prepare_fn):
            raise ValueError("isolated source preparation callback required")
        isolated_capture=isolated_source_prepare_fn(
            rpc,list(baseline_entries),list(source_probed))
        if (not isinstance(isolated_capture,dict)
                or isolated_capture.get("actionable") is not False
                or isolated_capture.get("broadcast") is not False
                or isolated_capture.get("baseline_control_unchanged") is False):
            raise ValueError("unsafe isolated source capture report")
    return {"status":"ISOLATED_RECENT_POOL_SOURCE_VERIFIED_AUDIT",
            "isolated_source_capture":isolated_capture,
            "isolated_sort_orders":list(sort_orders),
            "isolated_max_indexed_addresses_per_venue":pages*page_size*len(sort_orders),
            "source_verified_recent_pools":len(
                evidence["source_verified_new_pools"]),
            "source_reprobed_recent_pools":len(source_probed),
            "source_reprobe_failures":rejected,
            "incremental_topology_start_mints":len(
                set(all_later["three_hop_start_mints"])-before),
            "source_reprobed_incremental_topology_start_mints":len(
                set(later["three_hop_start_mints"])-before),
            "baseline_topology_start_mints":len(before),
            "venue_reports":evidence["venue_reports"],
            "admitted_to_primary_graph":False,
            "source_capture_verified":False,
            "signed_simulation_verified":False,**SAFE}
