"""Fifth venue: independent pure-integer DLMM bin-walk against authentic bytes.

This quotes captured source via separately maintained pure-Python integer DLMM
math (meteora-dlmm==0.5.0), independently of the official JS SDK.
No floating point, vault-constant-product approximation, simulation,
signing, registry admission or live broadcast.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from arb.meteora_dlmm_fifth_venue_source import CLOCK

SAFE={"actionable":False,"broadcast":False,"signed_parity_verified":False,
      "registry_admission_approved":False}


def _canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":")).encode()


def calculate(source,sdk):
    from meteora_dlmm import PoolState,quote
    if (not isinstance(source,dict) or source.get("venue")!="meteora_dlmm"
            or not isinstance(source.get("pools"),list) or
            not isinstance(sdk,dict) or sdk.get("venue")!="meteora_dlmm"
            or sdk.get("status")!="DLMM_SDK_SOURCE_QUOTES_NOT_NATIVE_PARITY"
            or not isinstance(sdk.get("pools"),list)):
        raise ValueError("DLMM authenticated source and official SDK reports required")
    originals={r.get("address"):r for r in source["pools"] if isinstance(r,dict)}
    if len(originals)!=len(source["pools"]):
        raise ValueError("duplicate DLMM source pool identity")
    if len(sdk["pools"])!=len(originals):
        raise ValueError("DLMM SDK/source distinct pool counts differ")
    verified=[]
    for sdkpool in sdk["pools"]:
        address=sdkpool.get("pool")
        row=originals.get(address)
        if row is None or row.get("status")!="AUTHENTICATED_BIN_SNAPSHOT_ONLY":
            raise ValueError("unauthenticated DLMM SDK pool")
        accounts=row.get("source_accounts")
        if (not isinstance(accounts,list) or len(accounts)!=25 or
                row.get("source_sha256")!=hashlib.sha256(_canonical({
                    "slot":row.get("source_slot"),"accounts":accounts})).hexdigest()
                or sdkpool.get("source_sha256")!=row["source_sha256"]
                or sdkpool.get("source_slot")!=row["source_slot"]):
            raise ValueError("DLMM source snapshot integrity or SDK binding mismatch")
        roles={r["address"]:r for r in accounts if "account_base64" in r}
        raw=lambda addr:base64.b64decode(roles[addr]["account_base64"],validate=True)
        mints=row["mints"]
        decimal_x=raw(mints[0])[44]
        decimal_y=raw(mints[1])[44]
        if any(x>18 for x in (decimal_x,decimal_y)):
            raise ValueError("unsupported DLMM decimals")
        bins=[raw(a["pda"]) for a in row["bin_arrays"] if a["authenticated"]]
        pool=PoolState.from_accounts(raw(address),bins,decimal_x,decimal_y,
                                     exhaustive=False)
        clock_bytes=raw(CLOCK)
        timestamp=int.from_bytes(clock_bytes[32:40],"little",signed=True)
        if timestamp!=row.get("fork_clock_unix_timestamp"):
            raise ValueError("DLMM quote Clock differs from source")
        trials=sdkpool.get("trials")
        if not isinstance(trials,list) or len(trials)!=4:
            raise ValueError("DLMM SDK four trial values required")
        observed=[]
        inputs=set()
        for trial in trials:
            if (not isinstance(trial,dict) or
                    trial.get("status")!="OFFICIAL_DLMM_SDK_SOURCE_QUOTE_ONLY"
                    or type(trial.get("swap_for_y")) is not bool or
                    type(trial.get("amount_in")) is not int
                    or not 0<trial["amount_in"]<2**64):
                raise ValueError("DLMM official SDK comparison invalid")
            forward=trial["swap_for_y"]
            mint_in=mints[0 if forward else 1]
            mint_out=mints[1 if forward else 0]
            amount=trial["amount_in"]
            key=(mint_in,amount)
            if (trial.get("input_mint")!=mint_in or
                    trial.get("output_mint")!=mint_out or key in inputs):
                raise ValueError("DLMM SDK direction/mint/size identity mismatch")
            inputs.add(key)
            sdk_in=int(trial["consumed_input"])
            sdk_out=int(trial["official_sdk_output"])
            if sdk_in!=amount or sdk_out<=0:
                raise ValueError("DLMM reference quote partial or zero")
            # Exactly reproduced integer-fee and bin-traversal quote from
            # the same captured bytes and on-chain Clock Unix timestamp.
            q=quote(pool,amount,forward,timestamp=timestamp,strict=True)
            if not q.complete or q.remaining_in!=0:
                raise ValueError("DLMM native quote incomplete")
            if q.amount_out!=sdk_out:
                raise ValueError("DLMM NATIVE_INTEGER_SDK_MISMATCH "+
                                 str(address)+" "+str(amount)+" "+
                                 str(q.amount_out)+" vs "+str(sdk_out))
            observed.append({"direction":"x_to_y" if forward else "y_to_x",
                "mint_in":mint_in,"mint_out":mint_out,"amount_in":amount,
                "official_sdk_output":sdk_out,"native_integer_output":q.amount_out,
                "bin_count":q.bins_crossed,
                "status":"DLMM_SOURCE_NATIVE_SDK_INTEGER_EXACT",
                "signed_parity_verified":False})
        if len({t["mint_in"] for t in observed})!=2 or any(
                sum(t["mint_in"]==mint for t in observed)!=2 for mint in mints):
            raise ValueError("DLMM four native reference trials incomplete")
        verified.append({"pool":address,"source_slot":row["source_slot"],
            "source_sha256":row["source_sha256"],"trials":observed})
    return {"venue":"meteora_dlmm","status":"DLMM_SOURCE_NATIVE_SDK_INTEGER_PARITY",
            "verified_pools":len(verified),"pools":verified,
            "native_pricing_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","sdk","output"):
        p.add_argument("--"+name,required=True)
    args=p.parse_args()
    result=calculate(json.loads(Path(args.source).read_text()),
                     json.loads(Path(args.sdk).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":result["verified_pools"]}))


if __name__=="__main__":
    main()
