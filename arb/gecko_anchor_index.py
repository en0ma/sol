"""Bounded GeckoTerminal anchor-pool hints (untrusted; on-chain checks mandatory)."""
import json
from urllib.request import Request, urlopen
from solders.pubkey import Pubkey
from arb.orca_whirlpool import SOL, USDC

MIN_LIQUIDITY_USD = 50000
MAX_PAGES_PER_ANCHOR = 2

def fetch_gecko_anchor_hints(anchors=(SOL, USDC)):
    pools, seen, errors = [], set(), []
    for anchor in anchors:
        for page in range(1, MAX_PAGES_PER_ANCHOR + 1):
            try:
                url = ("https://api.geckoterminal.com/api/v2/networks/solana/tokens/"
                       + anchor + "/pools?include=base_token,quote_token&page=" + str(page))
                req = Request(url, headers={"Accept": "application/json;version=20230203",
                                            "User-Agent": "sol-fork-research/1"})
                with urlopen(req, timeout=12) as resp:
                    raw = resp.read(524289)
                if len(raw) > 524288:
                    raise ValueError("GeckoTerminal response exceeds size cap")
                obj = json.loads(raw)
                included = {x["id"]: x for x in obj.get("included", [])
                            if isinstance(x, dict) and isinstance(x.get("id"), str)}
                if not isinstance(obj.get("data"), list):
                    raise ValueError("missing GeckoTerminal pools")
                for entry in obj["data"][:100]:
                    attrs = entry.get("attributes", {})
                    rel = entry.get("relationships", {})
                    try:
                        liquidity = float(attrs["reserve_in_usd"])
                        if not MIN_LIQUIDITY_USD <= liquidity < float("inf"):
                            continue
                        tokens = []
                        for role in ("base_token", "quote_token"):
                            token_id = rel[role]["data"]["id"]
                            token = included[token_id]["attributes"]["address"]
                            Pubkey.from_string(token)
                            tokens.append(token)
                        address = attrs["address"]
                        Pubkey.from_string(address)
                        dex = str(rel["dex"]["data"]["id"]).lower()
                    except (KeyError, ValueError, TypeError):
                        continue
                    if anchor not in tokens or tokens[0] == tokens[1]:
                        continue
                    venue = ("orca" if "orca" in dex else
                             "raydium_unclassified" if "raydium" in dex else
                             "meteora_unclassified" if "meteora" in dex else
                             "pumpswap" if "pump" in dex else None)
                    if venue is None or (venue, address) in seen:
                        continue
                    seen.add((venue, address))
                    pools.append({"address": address, "venue": venue, "mints": tokens,
                                  "index_liquidity_usd": liquidity,
                                  "candidate_source": "UNTRUSTED_GECKOTERMINAL"})
            except (OSError, TimeoutError, ValueError, KeyError) as exc:
                errors.append({"anchor": anchor, "page": page, "error": str(exc)[:200]})
                break
    return pools[:200], errors
