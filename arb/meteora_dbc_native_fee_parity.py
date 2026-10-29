"""Independent source-native DBC full exact-in fee + Q64 one-segment pricing.

The SDK is consulted only for final independent equality, NEVER for native
fee-excluded input or curve calculations. Fails closed on unsupported fee
schedulers, variable fees, Token-2022 and curve crossing. Does not sign.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from arb.meteora_dbc_native_segment import quote_one_segment
from arb.meteora_dbc_native_fee import price_with_fee

CFG_DISC=hashlib.sha256(b"account:PoolConfig").digest()[:8]


def parity(source,reference):
    if source.get("status")=="SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY":
        if (source.get("authenticated_source_pools")!=6
                or source.get("independent_audit",{}).get("authenticated_source_pools")!=6):
            raise ValueError("DBC independent six-source verification missing")
        source=source["source"]
    if (source.get("status")!="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"
            or reference.get("status")!="DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY"
            or source.get("signed_parity_verified") is not False):
        raise ValueError("DBC source and official reference evidence required")
    rows=source["source_pools"]
    other=reference["pools"]
    if len(rows)!=len(other) or len({r["pool"] for r in rows})!=len(rows):
        raise ValueError("DBC source pool/cardinality mismatch")
    sdk_by_pool={p["pool"]:p for p in other}
    if len(sdk_by_pool)!=len(other):raise ValueError("DBC duplicate official SDK pool")
    qualified=[]
    for row in rows:
        addr=row["pool"]; fields=row["pool_fields"]
        if (fields["pool_type"]!=0 or fields["is_migrated"]!=0
                or fields["migration_progress"]!=0 or
                fields["base_token_program"]!="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
                or fields["quote_token_program"]!="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"):
            raise ValueError("DBC native quote only supports original legacy SPL")
        if addr not in sdk_by_pool:
            raise ValueError("DBC original reference pool absent")
        quoted=sdk_by_pool[addr]
        entry=row["accounts"][fields["config"]]
        config=base64.b64decode(entry["account_base64"],validate=True)
        if (len(config)!=1048 or config[:8]!=CFG_DISC
                or hashlib.sha256(config).hexdigest()!=entry["sha256"]
                or quoted["source_config_sha256"]!=entry["sha256"]
                or quoted["source_pool_sha256"]!=row["accounts"][addr]["sha256"]
                or quoted["source_slot"]!=row["source_slot"]):
            raise ValueError("DBC native fee input does not match original source")
        # Zero-copy PoolState, 8-byte discriminator + 64-byte tracker + pubkeys.
        pool=base64.b64decode(row["accounts"][addr]["account_base64"],validate=True)
        if len(pool)!=424:raise ValueError("DBC original pool packed bytes invalid")
        activation=int.from_bytes(pool[296:304],"little")
        current=row["clock_slot"] if config[234]==0 else row["clock_unix_timestamp"] if config[234]==1 else None
        if current is None:raise ValueError("DBC unsupported activation point type")
        curve=[]
        for i in range(20):
            k=408+32*i
            sqrt=int.from_bytes(config[k:k+16],"little")
            liq=int.from_bytes(config[k+16:k+32],"little")
            if sqrt==0 or liq==0:break
            curve.append((sqrt,liq))
        if len(curve)!=1:
            raise ValueError("DBC original native multi-segment pricing requires separate acceptance")
        upper,liquidity=curve[0]
        start=int.from_bytes(config[392:408],"little")
        price=int(fields["sqrt_price_q64"])
        if not 0<start<price<upper:
            raise ValueError("DBC native source price outside original authenticated segment")
        sdk_trials=quoted["trials"]
        if len(sdk_trials)!=4:raise ValueError("DBC four distinct SDK quotes required")
        seen=set();results=[]
        for trial in sdk_trials:
            direction=trial["direction"];amount=int(trial["amount_in"])
            key=(direction,amount)
            if key in seen:raise ValueError("DBC duplicate signed-intent quote vector")
            seen.add(key)
            base=direction=="base_to_quote"
            def curve_quote(excluded):
                return quote_one_segment(
                    sqrt_price=price,liquidity=liquidity,
                    input_amount=excluded,base_for_quote=base,
                    target_price=start if base else upper)
            native=price_with_fee(config,direction=direction,amount_in=amount,
                    price_curve_fn=curve_quote,current_point=current,
                    activation_point=activation)
            checks={"actual_input_amount":"sdk_actual_input",
                    "output_amount":"sdk_output",
                    "next_sqrt_price":"sdk_next_sqrt_price",
                    "protocol_fee":"sdk_protocol_fee",
                    "trading_fee":"sdk_trading_fee"}
            if any(native[k]!=int(trial[ref]) for k,ref in checks.items()):
                raise ValueError("DBC independent native fees/curve disagree with official SDK")
            results.append({"direction":direction,"amount_in":amount,
              "native_output":native["output_amount"],
              "native_excluded_input":native["actual_input_amount"],
              "fee_numerator":native["fee_numerator"],
              "signed_swap_verified":False})
        if len({r["direction"] for r in results})!=2 or any(
                sum(r["direction"]==d for r in results)!=2
                for d in ("base_to_quote","quote_to_base")):
            raise ValueError("DBC exact-in directions not covered with two sizes")
        qualified.append({"pool":addr,"source_slot":row["source_slot"],
                 "source_pool_sha256":row["accounts"][addr]["sha256"],
                 "native_full_fee_sdk_trials_verified":4,
                 "trials":results,"signed_swap_verified":False})
    return {"status":"INDEPENDENT_DBC_ORIGINAL_NATIVE_FEE_CURVE_SDK_PARITY",
      "verified_pools":len(qualified),"verified_trials":len(qualified)*4,
      "pools":qualified,"supported_scope":"original SPL, single curve segment, static base fee scheduler, no transfer fee",
      "signed_parity_verified":False,"registry_admission_approved":False,
      "actionable":False,"broadcast":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source",required=True);ap.add_argument("--sdk",required=True)
    ap.add_argument("--output",required=True);a=ap.parse_args()
    result=parity(json.loads(Path(a.source).read_text()),
                  json.loads(Path(a.sdk).read_text()))
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
      "verified_pools":result["verified_pools"],
      "verified_trials":result["verified_trials"],
      "signed_verified":False}))


if __name__=="__main__":main()
