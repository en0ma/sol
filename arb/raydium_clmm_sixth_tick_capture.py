"""Read tracked Raydium CLMM tick liquidity in bounded source-only mode."""
import argparse,base64,hashlib,json
from pathlib import Path
from arb.rpc import call
from arb.raydium_clmm import decode,PROGRAM
from arb.raydium_clmm_tick_source import capture_tick_arrays

SAFE={"actionable":False,"broadcast":False,
      "native_pricing_verified":False,"signed_parity_verified":False,
      "registry_admission_approved":False}

def inspect(source,rpc,*,radius=4,attempts=4):
    if (not isinstance(source,dict) or source.get("venue")!="raydium_clmm"
            or not isinstance(source.get("pools"),list)):
        raise ValueError("authenticated Raydium CLMM source required")
    reports=[]
    for row in source["pools"]:
        if row.get("status")!="CLMM_AUTHENTICATED_SOURCE_NOT_SIGNED":
            raise ValueError("unverified Raydium CLMM pool candidate")
        errors=[]
        for _ in range(attempts):
            # Re-read the mutable CLMM pool immediately before one atomic
            # pool+tick array getMultipleAccounts. Its original slot must
            # NOT be misrepresented as the later tick-array snapshot slot.
            reply=call(rpc,"getAccountInfo",[row["address"],{
                "encoding":"base64","commitment":"confirmed"}])
            account=reply.get("value")
            if not isinstance(account,dict) or account.get("owner")!=PROGRAM:
                raise ValueError("CLMM tick capture pool owner changed")
            raw=base64.b64decode(account["data"][0],validate=True)
            state=decode(raw)
            if [state["token_mint_0"],state["token_mint_1"]]!=row["mints"]:
                raise ValueError("CLMM mint identities changed during tick capture")
            try:
                tick=capture_tick_arrays(rpc,row["address"],state,radius=radius)
            except ValueError as exc:
                if str(exc)!="CLMM pool price/fee state changed across tick-array read":
                    raise
                errors.append(str(exc))
                continue
            canonical=json.dumps(tick,sort_keys=True,separators=(",",":"))
            reports.append({"pool":row["address"],
                "authenticated_initial_source_slot":row["source_slot"],
                "authenticated_initial_source_sha256":row["source_sha256"],
                "tick_snapshot_sha256":hashlib.sha256(canonical.encode()).hexdigest(),
                "tick_capture":tick})
            break
        else:
            raise ValueError("CLMM mutable tick source could not be synchronized in bounded attempts")
    return {"venue":"raydium_clmm","status":"AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY",
            "pools":reports,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--rpc",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--radius",type=int,default=4)
    args=p.parse_args()
    result=inspect(json.loads(Path(args.source).read_text()),args.rpc,radius=args.radius)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"pools":len(result["pools"])}))
if __name__=="__main__":main()
