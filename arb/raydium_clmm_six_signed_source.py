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
from arb.raydium_clmm_native_single_tick import evaluate,quote_one_tick

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
            from arb.raydium_clmm_bitmap_extension_source import attach_authenticated_bitmap
            ticks=attach_authenticated_bitmap(rpc,address,ticks)
            # Derive two native-executable *size-aware* trials for each mint
            # without assuming a nine-decimal token can trade profitably at
            # 10k raw units. Require bounded single-tick exact-in and output
            # >100 base units for every directional sample.
            state_=ticks["synchronized_pool_state"]
            fee_=ticks["amm_config_source"]
            selected={}
            for forward,label in ((True,"zero_for_one"),(False,"one_for_zero")):
                eligible=[]
                for size in (10_000,20_000,100_000,200_000,1_000_000,
                             2_000_000,10_000_000,20_000_000,
                             100_000_000,200_000_000):
                    try:
                        quote=quote_one_tick(state_,fee_,size,
                                            zero_for_one=forward)
                        if quote["output"]>=100:
                            eligible.append(size)
                    except (ValueError,KeyError,TypeError):
                        pass
                    if len(eligible)==2:break
                if len(eligible)!=2:
                    raise ValueError("two non-dust bounded single-tick sizes not available "+label)
                selected[label]=eligible
            ticks["selected_amounts"]=selected
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
        # Retain a broader screened set. Official SDK independent review
        # may reject native candidates without admitting them as signed.
        if len(accepted)>=max(required*4,24):break
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
