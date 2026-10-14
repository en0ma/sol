"""Read-only quote scanner. Jupiter API key required; NEVER submits transactions.

Runs a SOL -> USDC -> SOL paper roundtrip. Quotes are sequential, not atomic.
Results are indicative ONLY; they cannot establish an executable opportunity.
"""
import json
import os
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from arb.core import Quote, evaluate_cycle

SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

def quote(api_key, input_mint, output_mint, amount):
    params = urlencode({"inputMint": input_mint, "outputMint": output_mint,
                        "amount": str(amount), "slippageBps": "30",
                        "instructionVersion": "V2"})
    req = Request("https://api.jup.ag/swap/v1/quote?" + params,
                  headers={"x-api-key": api_key, "Accept": "application/json"})
    with urlopen(req, timeout=15) as response:
        payload = json.load(response)
    if payload.get("error"):
        raise RuntimeError(payload["error"])
    labels = [entry.get("swapInfo", {}).get("label", "unknown")
              for entry in payload.get("routePlan", [])]
    return Quote(" / ".join(labels) or "unknown",
                 input_mint, output_mint, int(payload["inAmount"]),
                 int(payload["outAmount"]))

def main():
    key = os.environ.get("JUPITER_API_KEY")
    if not key:
        print("Set JUPITER_API_KEY to scan; no network requests made.", file=sys.stderr)
        return 2
    start = int(os.environ.get("START_SOL_LAMPORTS", "1000000000"))
    cost = int(os.environ.get("ESTIMATED_COST_SOL_LAMPORTS", "300000"))
    first = quote(key, SOL, USDC, start)
    second = quote(key, USDC, SOL, first.out_amount)
    result = evaluate_cycle([first, second], start, cost)
    print(json.dumps({"disclaimer": "Sequential off-chain quotes, not atomic executable PnL",
                      "quotes": [q.__dict__ for q in [first, second]],
                      "evaluation": result}, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
