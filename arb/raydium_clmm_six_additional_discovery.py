"""Research-only discovery of additional Raydium CLMM pool identity hints.

The canonical Raydium API is an UNTRUSTED hint source, not proof of
authenticity. Every candidate must pass the Solana on-chain CLMM program
owner, pool mints, vaults, fee config, tick-array and signed SDK/native
four-swap gates before it can enter the single shared registry.
No signing, RPC writes, mainnet sends or registry mutations here.
"""
import argparse,json,urllib.request
from pathlib import Path
from solders.pubkey import Pubkey
from arb.raydium_clmm import PROGRAM

BASE="https://api-v3.raydium.io/pools/info/list-v2"
SAFE={"actionable":False,"broadcast":False,"signed_parity_verified":False,
      "registry_admission_approved":False}

def discover(registry,*,minimum=6,limit=80,fetch=None):
    if (not isinstance(registry,dict) or not isinstance(registry.get("pools"),list)
            or type(minimum) is not int or minimum<1 or minimum>6
            or type(limit) is not int or not minimum<=limit<=100):
        raise ValueError("bounded Raydium source-discovery arguments invalid")
    existing={r.get("address") for r in registry["pools"]
              if isinstance(r,dict) and r.get("venue")=="raydium_clmm"}
    get=fetch or (lambda url:json.load(urllib.request.urlopen(url,timeout=20)))
    url=BASE+"?size="+str(limit)+"&poolType=Concentrated&sortField=liquidity&sortType=desc"
    page=get(url)
    if not isinstance(page,dict) or page.get("success") is not True:
        raise ValueError("official Raydium discovery API failed")
    obj=page.get("data",{})
    rows=obj.get("data") if isinstance(obj,dict) else None
    if not isinstance(rows,list):
        raise ValueError("official Raydium API response lacks pool list")
    results=[];seen=set(existing)
    for item in rows:
        if not isinstance(item,dict) or item.get("programId")!=PROGRAM:
            continue
        if item.get("type")!="Concentrated" or item.get("hasDynamicFee") is True:
            continue
        if str(item.get("feeOn","0")) not in ("0","input","Input"):
            continue
        address=item.get("id")
        x=item.get("mintA")
        y=item.get("mintB")
        if (not isinstance(address,str) or address in seen
                or not isinstance(x,dict) or not isinstance(y,dict)):
            continue
        mint_x=x.get("address");mint_y=y.get("address")
        if not isinstance(mint_x,str) or not isinstance(mint_y,str) or mint_x==mint_y:
            continue
        try:
            for public in (address,mint_x,mint_y):Pubkey.from_string(public)
        except ValueError:
            continue
        # Match the existing signed simple-token subset to avoid carrying
        # an unsafe Token-2022 extension account through a legacy token path.
        if (x.get("programId") not in (None,"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
                or y.get("programId") not in (None,"TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")):
            continue
        seen.add(address)
        results.append({"venue":"raydium_clmm","address":address,
            "mints":[mint_x,mint_y],"candidate_status":"OFFICIAL_API_HINT_NOT_AUTHENTICATED"})
    return {"venue":"raydium_clmm","status":"OFFICIAL_RAYDIUM_API_HINTS_ONLY",
        "requested_additional":minimum,"hinted":len(results),"pools":results,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--registry",default="arb/pool_registry.json")
    p.add_argument("--minimum",type=int,default=6)
    p.add_argument("--limit",type=int,default=80)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    registry=json.loads(Path(args.registry).read_text())
    report=discover(registry,minimum=args.minimum,limit=args.limit)
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"hinted":report["hinted"]}))
    if report["hinted"]<args.minimum:
        raise SystemExit("fewer than six genuine Raydium pool hints")
if __name__=="__main__":main()
