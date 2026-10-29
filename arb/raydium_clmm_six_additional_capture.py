"""Authenticate six *new* Raydium CLMM candidates from official API hints.

Strictly separate untrusted discovery API from the actual on-chain
program-owned PoolState/vaults/mints/fee config. No signed or registry
admission without the genuine Surfpool native/SDK/SPL full proof.
"""
import argparse,json
from pathlib import Path
from arb.raydium_clmm_sixth_venue_source import capture_pool
from arb.raydium_clmm_six_additional_discovery import SAFE

def capture(rpc,registry,hints,*,required=6):
    if (not isinstance(hints,dict) or hints.get("status")!="OFFICIAL_RAYDIUM_API_HINTS_ONLY"
            or hints.get("venue")!="raydium_clmm"
            or type(required) is not int or not 1<=required<=6):
        raise ValueError("invalid Raydium untrusted CLMM discovery input")
    recorded={r["address"] for r in registry["pools"] if r.get("venue")=="raydium_clmm"}
    accepted=[];rejected=[];seen=set(recorded)
    for candidate in hints.get("pools",[]):
        address=candidate.get("address")
        if (not isinstance(address,str) or address in seen
                or candidate.get("candidate_status")!="OFFICIAL_API_HINT_NOT_AUTHENTICATED"):
            continue
        seen.add(address)
        try:
            row=capture_pool(rpc,address,candidate.get("mints"))
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            rejected.append({"address":address,"reason":str(exc)[:180]})
            continue
        if row["status"]!="CLMM_AUTHENTICATED_SOURCE_NOT_SIGNED":
            raise ValueError("CLMM source authentication returned invalid status")
        accepted.append(row)
        if len(accepted)>=required:
            break
    return {"venue":"raydium_clmm",
        "status":"SIX_ADDITIONAL_ONCHAIN_AUTHENTICATED_NOT_SIGNED",
        "required":required,"authenticated":len(accepted),
        "pools":accepted,"rejected":rejected,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("rpc","registry","hints","output"):p.add_argument("--"+name,required=True)
    p.add_argument("--required",type=int,default=6)
    args=p.parse_args()
    result=capture(args.rpc,json.loads(Path(args.registry).read_text()),
        json.loads(Path(args.hints).read_text()),required=args.required)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
                      "authenticated":result["authenticated"],
                      "rejected":len(result["rejected"])}))
    if result["authenticated"]<args.required:
        raise SystemExit("six extra *authenticated* Raydium CLMM pools unavailable")
if __name__=="__main__":main()
