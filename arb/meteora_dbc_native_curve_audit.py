"""Independent Q64 DBC curve-only audit on source bytes and official SDK receipts.

The math is not copied from SDK outputs: decode the 1048-byte onchain PoolConfig
and reconstruct each exact-input curve result from independent Python integers.
SDK's actualInputAmount is provided as a FEE BOUNDARY, not independent fee parity.
No claim about fee scheduler, Token-2022 transfers, signed swaps or registry.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from arb.meteora_dbc_native_curve_walk import walk

CONFIG_SIZE=1048
CFG_DISC=hashlib.sha256(b"account:PoolConfig").digest()[:8]


def audit(source, sdk):
    if source.get("status")=="SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY":
        if (source.get("authenticated_source_pools")!=6 or
                source.get("independent_audit",{}).get("authenticated_source_pools")!=6):
            raise ValueError("DBC six original source audits missing")
        source=source["source"]
    if (source.get("status")!="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"
            or sdk.get("status")!="DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY"
            or source.get("signed_parity_verified") is not False
            or sdk.get("signed_verified") is not False):
        raise ValueError("DBC original source and unsigned SDK reports required")
    rows=source["source_pools"]
    reference=sdk["pools"]
    if len(rows)!=len(reference) or len({r["pool"] for r in rows})!=len(rows):
        raise ValueError("DBC SDK and source pool cardinality mismatch")
    quotes={r["pool"]:r for r in reference}
    outputs=[]
    for row in rows:
        pool=row["pool"]
        if pool not in quotes:
            raise ValueError("DBC SDK pool identity absent")
        sdk_row=quotes[pool]
        fields=row["pool_fields"]
        cfg_entry=row["accounts"][fields["config"]]
        raw=base64.b64decode(cfg_entry["account_base64"],validate=True)
        if (len(raw)!=CONFIG_SIZE or raw[:8]!=CFG_DISC
                or hashlib.sha256(raw).hexdigest()!=cfg_entry["sha256"]
                or sdk_row["source_pool_sha256"]!=row["accounts"][pool]["sha256"]
                or sdk_row["source_config_sha256"]!=cfg_entry["sha256"]
                or sdk_row["source_slot"]!=row["source_slot"]):
            raise ValueError("DBC original source identity or config digest mismatch")
        start=int.from_bytes(raw[392:408],"little")
        curve=[]
        for i in range(20):
            offset=408+32*i
            point=int.from_bytes(raw[offset:offset+16],"little")
            liquidity=int.from_bytes(raw[offset+16:offset+32],"little")
            if point==0 or liquidity==0:break
            curve.append((point,liquidity))
        if not curve:
            raise ValueError("DBC source curve empty")
        upper=curve[-1][0]
        price=int(fields["sqrt_price_q64"])
        migration_price=int.from_bytes(raw[280:296],"little")
        if not (0<start<price<upper and migration_price>=price):
            raise ValueError("DBC source sqrt price outside authenticated curve")
        trials=sdk_row["trials"]
        if len(trials)!=4:
            raise ValueError("DBC expected two directions and two trial sizes")
        seen=set()
        verified=[]
        for trial in trials:
            direction=trial["direction"]
            if direction not in ("base_to_quote","quote_to_base"):
                raise ValueError("DBC unsupported source direction")
            amount=int(trial["amount_in"])
            actual=int(trial["sdk_actual_input"])
            key=(direction,amount)
            if amount<=0 or key in seen or not 0<actual<=amount:
                raise ValueError("DBC trial intent/dust/uniqueness invalid")
            seen.add(key)
            base=direction=="base_to_quote"
            native=walk(sqrt_price=price,curve=curve,
                amount_in=actual,base_for_quote=base,
                sqrt_start_price=start,migration_sqrt_price=migration_price)
            if int(trial["sdk_next_sqrt_price"])!=native["next_sqrt_price"]:
                raise ValueError("DBC independent curve next price differs from official SDK")
            gross=int(trial["sdk_output"])
            if base:
                gross+=int(trial["sdk_trading_fee"])+int(trial["sdk_protocol_fee"])
            if gross!=native["output_amount"]:
                raise ValueError("DBC independent zero-fee curve gross output differs from SDK")
            verified.append({"direction":direction,"input":amount,
                "sdk_fee_excluded_input":actual,"native_gross_output":gross,
                "next_sqrt_price":native["next_sqrt_price"]})
        if len({x["direction"] for x in verified})!=2:
            raise ValueError("DBC both swap directions required")
        outputs.append({"pool":pool,"source_slot":row["source_slot"],
            "source_config_sha256":cfg_entry["sha256"],
            "curve_math_trials_verified":4,"trials":verified,
            "fee_scheduler_independently_verified":False,
            "native_full_quote_parity_verified":False,
            "signed_swap_verified":False})
    return {"status":"DBC_INDEPENDENT_BOUNDED_CURVE_MATH_ONLY",
        "curve_math_verified_pools":len(outputs),"trials_verified":len(outputs)*4,
        "pools":outputs,"fee_scheduler_independently_verified":False,
        "native_full_quote_parity_verified":False,"signed_parity_verified":False,
        "registry_admission_approved":False,"actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--sdk",required=True)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    result=audit(json.loads(Path(a.source).read_text()),
                 json.loads(Path(a.sdk).read_text()))
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
                      "trials_verified":result["trials_verified"],
                      "signed_verified":False}))


if __name__=="__main__":main()
