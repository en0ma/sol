"""Honest coverage report: pool identity != quote or execution capability."""
import json,os
from arb.onchain_pool_discovery import VENUES
from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED
from arb.pool_registry import refresh
from arb.rpc import call

# Only adapters with demonstrated signed atomic simulation, not guessed availability.
from arb.venue_capabilities import SWAP_BUILDERS, SIGNED_SWAP_VENUES
SIMULATED_SWAP_VENUES=SIGNED_SWAP_VENUES
# Amount-aware quote support is not assumed from a pool decoder or swap builder.
NATIVE_AMOUNT_QUOTE_VENUES=set()

def summarize(verified_pools):
    unique={(p["venue"],p["address"]) for p in verified_pools if p.get("verified")}
    pools=[p for p in verified_pools if p.get("verified")]
    by_venue={}
    for venue in sorted(VENUES):
        addresses={p["address"] for p in pools if p["venue"]==venue}
        by_venue[venue]={"validated_pools":len(addresses),
                         "decoder":True,
                         "signed_swap_simulated":venue in SIMULATED_SWAP_VENUES,
                         "swap_instruction_builder":venue in SWAP_BUILDERS,
                         "amount_aware_native_quote":venue in NATIVE_AMOUNT_QUOTE_VENUES}
    for venue in sorted(set(RECOGNIZED_UNSUPPORTED.values())):
        by_venue[venue]={"validated_pools":0,"decoder":False,
                         "signed_swap_simulated":False,"amount_aware_native_quote":False}
    mints={mint for p in pools for mint in p["mints"]}
    return {"validated_pools":len(unique),"distinct_tokens":len(mints),
            "recognized_protocol_families":len(by_venue),
            "decoded_venue_families":len(VENUES),
            "venues_with_signed_swap_simulation":sum(v["signed_swap_simulated"] for v in by_venue.values()),
            "venues_with_native_amount_quotes":sum(v["amount_aware_native_quote"] for v in by_venue.values()),
            "by_venue":by_venue,
            "arb_scanner_profitability_ready":False,
            "note":"Decoder, swap-building and native amount-aware quoting are separate capability gates."}

def main():
    from arb.arbitrage_mission import check
    check()
    entries=json.load(open("arb/pool_registry.json"))["pools"]
    report=refresh(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"),entries)
    result=summarize(report["verified_pools"])
    result["registry_rejected"]=report["rejected"]
    print(json.dumps(result,indent=2))
    if os.environ.get("VENUE_COVERAGE_REPORT"):
        with open(os.environ["VENUE_COVERAGE_REPORT"],"w") as f:json.dump(result,f,indent=2)
    return 0 if not report["rejected"] else 2
if __name__=="__main__":raise SystemExit(main())
