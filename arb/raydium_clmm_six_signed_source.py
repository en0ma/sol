"""Select 6 *new* genuine Raydium CLMM pools with four native exact-in
single-tick candidates each, using only original verified pool identities.

Fetch independent authenticated synced pool/config/vault/ticks, bind
cryptographic source hash, reject all unsupported dynamic/limit order quote
paths. The result is NOT signed admission. It is the input to official
SDK and actual 4-swap-per-pool Surfpool validation.
"""
import argparse,hashlib,json
from pathlib import Path
from arb.raydium_clmm_sixth_venue_source import capture_pool
from arb.raydium_clmm_tick_source import capture_tick_arrays
from arb.raydium_clmm_native_single_tick import evaluate

def select(rpc,registry,hints,*,required=6):
    if type(required) is not int or not 1<=required<=6:
        raise ValueError("six pool source acceptance bound required")
    seen={p.get("address") for p in registry["pools"]
          if isinstance(p,dict) and p.get("venue")=="raydium_clmm"}
    accepted=[];rejected=[]
    for candidate in hints["pools"]:
        address=candidate["address"]
        if address in seen:continue
        seen.add(address)
        try:
            source=capture_pool(rpc,address,candidate.get("mints"))
            # getAccountInfo discovers initial roles, followed by exact
            # same-slot refreshed pool/ticks/config and vaults. Source audit
            # remains bound to the latter price, never the initial slot.
            from arb.rpc import call
            from arb.raydium_clmm import decode
            import base64
            for _ in range(4):
                fresh=call(rpc,"getAccountInfo",[address,{
                    "encoding":"base64","commitment":"confirmed"}])["value"]
                state=decode(base64.b64decode(fresh["data"][0],validate=True))
                try:
                    ticks=capture_tick_arrays(rpc,address,state,radius=4)
                    break
                except ValueError as exc:
                    if "state changed across tick-array read" not in str(exc):raise
            else:raise ValueError("CLMM changing price could not synchronize")
            row={"pool":address,"authenticated_initial_source_slot":source["source_slot"],
                "authenticated_initial_source_sha256":source["source_sha256"],
                "tick_capture":ticks}
            row["tick_snapshot_sha256"]=hashlib.sha256(json.dumps(
                ticks,sort_keys=True,separators=(",",":")).encode()).hexdigest()
            report={"venue":"raydium_clmm",
                "status":"AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY",
                "pools":[row],"actionable":False,"broadcast":False,
                "native_pricing_verified":False,"signed_parity_verified":False,
                "registry_admission_approved":False}
            native=evaluate(report)
            if len(native["pools"][0]["quotes"])!=4 or native["pools"][0]["blocked"]:
                raise ValueError("four genuine single-tick integer quotes not available: "+
                                 str(native["pools"][0]["blocked"])[:180])
            accepted.append(row)
        except (ValueError,KeyError,TypeError,RuntimeError,OSError) as exc:
            rejected.append({"address":address,"reason":str(exc)[:190]})
        if len(accepted)>=required:break
    result={"venue":"raydium_clmm",
        "status":"AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY",
        "pools":accepted,"rejected":rejected,
        "actionable":False,"broadcast":False,
        "signed_parity_verified":False,"native_pricing_verified":False,
        "registry_admission_approved":False}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("rpc","registry","hints","output"):p.add_argument("--"+name,required=True)
    p.add_argument("--required",type=int,default=6)
    a=p.parse_args()
    result=select(a.rpc,json.loads(Path(a.registry).read_text()),
        json.loads(Path(a.hints).read_text()),required=a.required)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"eligible":len(result["pools"]),
                      "rejected":len(result["rejected"]),
                      "status":result["status"]}))
    if len(result["pools"])<a.required:
        raise SystemExit("six new genuinely quote-eligible CLMM pool source snapshots not found")
if __name__=="__main__":main()
