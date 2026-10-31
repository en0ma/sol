"""DBC read-only public pool identity discovery. Index data is never proof.

DexPaprika's meteora_dbc classification is an untrusted locator only.
Every resulting address must be checked through the original DBC program's
actual getMultipleAccounts owner, discriminator and dependent-account gates.
"""
import argparse
import json
import urllib.parse
import urllib.request
from pathlib import Path
from solders.pubkey import Pubkey

URL = "https://api.dexpaprika.com/networks/solana/pools/search"


def discover(*, count=6, fetch=None):
    if type(count) is not int or not 1 <= count <= 6:
        raise ValueError("DBC pool hint count must be 1-6")
    def remote(url):
        req=urllib.request.Request(url,headers={
            "User-Agent":"sol-offline-dbc-research/1.0",
            "Accept":"application/json"})
        with urllib.request.urlopen(req,timeout=20) as response:
            return json.load(response)
    url=URL+"?"+urllib.parse.urlencode({
        "dex_name":"meteora_dbc", "order_by":"volume_usd_24h",
        "sort":"desc","limit":50
    })
    page=(fetch or remote)(url)
    if not isinstance(page,dict) or not isinstance(page.get("results"),list):
        raise ValueError("DBC public index response unavailable")
    accepted=[];seen=set()
    for row in page["results"]:
        if not isinstance(row,dict):
            continue
        # A public index is a locator only; no token/mint/config claims.
        address=row.get("address") or row.get("pool_address")
        if not isinstance(address,str) or address in seen:
            continue
        try:
            if str(Pubkey.from_string(address)) != address:
                continue
        except ValueError:
            continue
        seen.add(address)
        accepted.append({"address":address,
          "status":"UNTRUSTED_PUBLIC_DBC_POOL_HINT_NOT_SOURCE_VERIFIED"})
        if len(accepted)>=count:break
    return {"venue":"meteora_dbc","status":"UNTRUSTED_IDENTITIES_ONLY",
      "provider":"dexpaprika_meteora_dbc","hints":accepted,
      "authenticated_pools":0,"signed_verified_pools":0,
      "actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--count",type=int,default=3)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=discover(count=args.count)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"hint_count":len(result["hints"]),
                      "authenticated_pools":0,"signed_verified_pools":0}))
    if len(result["hints"])<args.count:
        raise SystemExit("DBC public pool hint target not reached")


if __name__=="__main__":
    main()
