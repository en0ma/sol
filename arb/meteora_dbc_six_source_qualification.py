"""Bounded six original Meteora DBC pool source qualification.

Only original account bytes + independent source audits; six successful pool
identities do NOT imply six SDK/native quote parities or 24 signed swaps.
"""
import argparse,json,os,subprocess,tempfile
from pathlib import Path
from arb.meteora_dbc_seventh_candidate_capture import run
from arb.meteora_dbc_seventh_source_audit import independently_audit
from arb.meteora_dbc_native_fee_parity import parity as native_fee_parity
from arb.meteora_dbc_native_curve_audit import audit as native_curve_audit


def qualify(rpc, *, count=6, hint_limit=24, pages=4):
    if type(count) is not int or count!=6:
        raise ValueError("DBC seventh venue six distinct source pools required")
    captured=run(rpc,count=count,hint_limit=hint_limit,pages=pages,strict=False)
    addresses=[p["pool"] for p in captured["source_pools"]]
    if len(addresses)!=6 or len(set(addresses))!=6:
        raise ValueError("DBC six unique pool identities not established")
    audit=independently_audit(captured)
    if audit["authenticated_source_pools"]!=6:
        raise ValueError("DBC six independent original source audits incomplete")
    return {"venue":"meteora_dbc","status":"SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY",
        "source":captured,"independent_audit":audit,
        "authenticated_source_pools":6,"native_pricing_verified":False,
        "official_sdk_parity_verified":False,"signed_swaps_verified":0,
        "signed_parity_verified":False,"registry_admission_approved":False,
        "actionable":False,"broadcast":False}



def validate_official_sdk_candidate(row):
    """Reject an authenticated but unquotable launch before it occupies a slot.

    This is screening only: independent native and signed acceptance remain
    mandatory downstream. No public RPC or signing is performed by the oracle.
    """
    source={"status":"DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED",
            "source_pools":[row],"signed_parity_verified":False}
    with tempfile.TemporaryDirectory(prefix="dbc-sdk-screen-") as directory:
        src=Path(directory)/"source.json"
        out=Path(directory)/"sdk.json"
        src.write_text(json.dumps(source)+"\n")
        result=subprocess.run(["node","tools/meteora_dbc_official_sdk_oracle.js",
                               str(src),str(out)],capture_output=True,text=True,
                              timeout=30,check=False)
        if result.returncode!=0:
            # Fail closed; never let a zero-liquidity source count as a
            # six-pool quote candidate. Avoid leaking source or RPC data.
            raise ValueError("DBC official SDK bidirectional quote screening failed")
        report=json.loads(out.read_text())
        pools=report.get("pools",[])
        if (len(pools)!=1 or pools[0].get("pool")!=row["pool"] or
                len(pools[0].get("trials",[]))!=4 or
                {t["direction"] for t in pools[0]["trials"]}!=
                {"base_to_quote","quote_to_base"}):
            raise ValueError("DBC official SDK four bidirectional quotes missing")
        curve=native_curve_audit(source,report)
        if (curve.get("curve_math_verified_pools")!=1 or
                curve.get("trials_verified")!=4):
            raise ValueError("DBC independent source-native curve parity missing")
        native=native_fee_parity(source,report)
        if native.get("verified_pools")!=1 or native.get("verified_trials")!=4:
            raise ValueError("DBC independent full-fee native/SDK parity missing")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--pages",type=int,default=12)
    a=p.parse_args()
    captured=run(a.rpc,count=6,hint_limit=24,pages=a.pages,strict=False,
                 candidate_validator=validate_official_sdk_candidate)
    count=len(captured["source_pools"])
    audit=(independently_audit(captured) if count else
           {"authenticated_source_pools":0,"pools":[],
            "signed_parity_verified":False})
    if audit["authenticated_source_pools"]!=count:
        raise SystemExit("DBC original source audit count mismatch")
    complete=(count==6 and len({p["pool"] for p in captured["source_pools"]})==6)
    result={"venue":"meteora_dbc",
       "status":"SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY" if complete else
                "PARTIAL_DBC_ORIGINAL_SOURCE_EVIDENCE_NOT_ACCEPTED",
       "source":captured,"independent_audit":audit,
       "authenticated_source_pools":count,"target_source_pools":6,
       "native_pricing_verified":False,"signed_swaps_verified":0,
       "signed_parity_verified":False,"registry_admission_approved":False,
       "actionable":False,"broadcast":False}
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
       "authenticated_source_pools":count,"target":6,
       "signed_swaps_verified":0}))
    if not complete:
        raise SystemExit("DBC six independently authenticated pools not reached")


if __name__=="__main__":main()
