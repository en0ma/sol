"""Bounded Raydium-indexer address hints, independently verified on source fork.

Raydium CPMM supports random signer-created pool addresses, so deterministic
PDA derivation cannot find them. The indexer is UNTRUSTED discovery only.
Every candidate is fetched using local source-backed RPC, decoded with the
pinned CPMM state layout and passed through the existing SPL vault verifier.
Never trust indexer prices, token identity, pool ownership or liquidity.

This is source topology discovery, never executable quote or signed evidence.
"""
import base64
from arb.raydium_cpmm import PROGRAM,decode,api_candidate_addresses
from arb.onchain_pool_discovery import verify
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.m5_start_mint_expansion import topology

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}


def discover(rpc,entries,*,pages=3,page_size=100,maximum_verify=48,
             index_fn=None,call_fn=None,verify_fn=None):
    """Return authenticated source-pool additions, ordered by topology gain."""
    local_rpc_only(rpc)
    if (not isinstance(entries,list)
            or type(pages)is not int or not 1<=pages<=10
            or type(page_size)is not int or not 1<=page_size<=100
            or type(maximum_verify)is not int or not 1<=maximum_verify<=96):
        raise ValueError("invalid bounded Raydium indexer discovery budget")
    known={(e["venue"],e["address"]) for e in entries}
    index=index_fn or api_candidate_addresses
    try:
        candidates=index(pages=pages,page_size=page_size)
    except (ValueError,RuntimeError,TypeError,KeyError,OSError,TimeoutError) as exc:
        # The indexer may be unavailable. Never print exception text: URLs
        # can contain secrets, and indexer failures are NOT source evidence.
        return {"status":"UNTRUSTED_INDEXER_UNAVAILABLE",
                "indexer_exception_class":type(exc).__name__,
                "indexed_addresses":0,"source_accounts_checked":0,
                "verified_new_pool_count":0,"source_verified_new_pools":[],
                "additional_topology_start_mints":[],
                "indexer_is_not_source_evidence":True,
                "signed_simulation_verified":False,**SAFE}
    if not isinstance(candidates,list) or len(candidates)>pages*page_size:
        raise ValueError("unbounded or malformed Raydium indexer response")
    addresses=[]
    seen=set()
    for row in candidates:
        if (not isinstance(row,dict) or row.get("venue")!="raydium_cpmm"
                or not isinstance(row.get("address"),str)
                or not 32<=len(row["address"])<=44):
            raise ValueError("malformed untrusted indexer pool hint")
        address=row["address"]
        if address not in seen and ("raydium_cpmm",address) not in known:
            addresses.append(address)
        seen.add(address)
    fetch=call_fn or call
    source_candidates=[]
    invalid_source=0
    for offset in range(0,len(addresses),100):
        group=addresses[offset:offset+100]
        response=fetch(rpc,"getMultipleAccounts",[group,
            {"encoding":"base64","commitment":"confirmed"}])
        accounts=response.get("value") if isinstance(response,dict) else None
        if not isinstance(accounts,list) or len(accounts)!=len(group):
            raise ValueError("missing source-fork indexed pool account evidence")
        for address,account in zip(group,accounts):
            if not account:
                continue
            try:
                if account.get("owner")!=PROGRAM or account.get("executable") is not False:
                    raise ValueError("wrong source pool program")
                state=decode(base64.b64decode(account["data"][0],validate=True))
                a,b=state["token_0_mint"],state["token_1_mint"]
                if not isinstance(a,str) or not isinstance(b,str) or a==b:
                    raise ValueError("invalid source pool mint identity")
                source_candidates.append((address,state,a,b))
            except (ValueError,KeyError,TypeError):
                invalid_source+=1
    # Only source-decoded mints determine how a candidate contributes to
    # missing triangles; no indexer token or price fields are consulted.
    base=topology(entries)
    before=set(base["three_hop_start_mints"])
    # Indexer hints are useful ONLY as source-decoded candidate identities.
    # A missing triangle may need TWO new edges: A-B and A-C can close
    # A-B-C-A if B-C already exists. Ranking each pool independently
    # gives both zero immediate gain and can starve the combination.
    existing_pairs={frozenset(row["mints"]) for row in entries}
    old_neighbors={mint:set(peers) for mint,peers in
                   base["mint_neighbors"].items()}
    candidate_pairs={frozenset((a,b)) for _,_,a,b in source_candidates}
    priorities=[]
    complementary_addresses=0
    for address,state,a,b in source_candidates:
        edge={"venue":"raydium_cpmm","address":address,"mints":[a,b]}
        gained=set(topology(entries+[edge])["three_hop_start_mints"])-before
        # Count eligible triangle participants, not an unverified pool as
        # proof. A complementary edge needs a separate source verification.
        potential=set()
        for c in old_neighbors.get(a,set()):
            if c!=b and frozenset((b,c)) in candidate_pairs:
                potential.update((a,b,c))
        for c in old_neighbors.get(b,set()):
            if c!=a and frozenset((a,c)) in candidate_pairs:
                potential.update((a,b,c))
        new_potential=len(potential-before)
        if new_potential:
            complementary_addresses+=1
        novel_pair=int(frozenset((a,b)) not in existing_pairs)
        priorities.append((len(gained),new_potential,novel_pair,
                           address,state,a,b))
    priorities.sort(key=lambda item:(-item[0],-item[1],-item[2],item[3]))
    selected=[]
    failures=0
    verifier=verify_fn or verify
    for _,_,_,address,state,a,b in priorities[:maximum_verify]:
        try:
            result=verifier(rpc,"raydium_cpmm",address,state)
            if (not isinstance(result,dict)
                    or result.get("venue")!="raydium_cpmm"
                    or result.get("address")!=address
                    or type(result.get("slot")) is not int
                    or result["slot"]<0
                    or sorted(result.get("mints",[]))!=sorted((a,b))
                    or result.get("swap_simulated") is not False):
                raise ValueError("source pool/vault verification mismatch")
            selected.append({"venue":"raydium_cpmm","address":address,
                "mints":result["mints"],"source_verified_slot":result["slot"],
                "source_verified_only":True})
        except (ValueError,KeyError,TypeError,RuntimeError,OSError):
            failures+=1
    after=topology(entries+selected)
    return {"status":"SOURCE_REVERIFIED_UNTRUSTED_RAYDIUM_INDEXER_HINTS",
            "indexer_is_not_source_evidence":True,
            "indexed_addresses":len(candidates),
            "new_candidate_addresses":len(addresses),
            "source_accounts_checked":len(addresses),
            "source_decoded_candidate_pools":len(source_candidates),
            "complementary_edge_candidates":complementary_addresses,
            "complementary_edge_priority_policy":
                "DIRECT_TRIANGLE_GAIN_THEN_TWO_EDGE_POTENTIAL_THEN_NEW_PAIR",
            "source_verification_attempts":min(len(priorities),maximum_verify),
            "source_verification_failures":failures,
            "invalid_source_account_count":invalid_source,
            "verified_new_pool_count":len(selected),
            "source_verified_new_pools":selected,
            "additional_topology_start_mints":sorted(
                set(after["three_hop_start_mints"])-before),
            "signed_simulation_verified":False,**SAFE}
