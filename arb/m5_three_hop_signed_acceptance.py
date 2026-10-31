"""Independent strict signed three-hop acceptance from actual isolated receipts.

Only real signed Surfpool CPI, positive post-balances and last-leg rollback
qualify. Never infer protocol-exact quote accuracy or live profitability.
"""
import argparse
import json
from pathlib import Path

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
PAIRS=(("raydium_cpmm","raydium_amm_v4"),("raydium_amm_v4","raydium_cpmm"))

def assess(route,receipt):
    errors=[]
    venues=[route[0],route[1],route[0]]
    if receipt.get("route_venues")!=venues or receipt.get("legs")!=3:
        errors.append("three ordered signed venues missing")
    if receipt.get("status")!="SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED":
        errors.append("signed positive/negative execution not accepted")
    for k in ("signed_cpi_per_leg_verified","rollback_failure_case_verified",
              "signed_atomic_simulation_verified"):
        if receipt.get(k) is not True:errors.append("missing "+k)
    for k,v in SAFE.items():
        if receipt.get(k) is not v:errors.append("unsafe "+k)
    if receipt.get("execution_environment")!="ISOLATED_SURFPOOL_OFFLINE":
        errors.append("source execution environment absent")
    if receipt.get("quote_accuracy_verified") is not False or receipt.get("source_snapshot_slot") is not None:
        errors.append("unsupported pricing/source attestation")
    amounts=receipt.get("planned_inputs")
    hops=receipt.get("cpi_hops")
    post=receipt.get("positive_post_balances_base_units")
    if not isinstance(amounts,list) or len(amounts)!=3 or any(type(x)is not int or not 0<x<2**64 for x in amounts):
        errors.append("three signed planned inputs missing")
    if not isinstance(hops,list) or len(hops)!=2:
        errors.append("two signed CPI intermediate hops missing")
    elif isinstance(amounts,list) and len(amounts)==3:
        for i,hop in enumerate(hops,1):
            if not isinstance(hop,dict) or hop.get("hop")!=i or not isinstance(hop.get("account"),str) or not hop["account"] or any(hop.get(k)!=amounts[i] for k in ("planned_input_base_units","received_base_units","consumed_base_units")):
                errors.append("signed full CPI consumption mismatch hop "+str(i))
    if not isinstance(post,list) or len(post)!=4 or post[:3]!=[0,0,0] or type(post[3]) is not int or post[3]<=0:
        errors.append("final signed SPL balances unverified")
    if type(receipt.get("signed_packet_bytes")) is not int or not 100<=receipt["signed_packet_bytes"]<=1232:
        errors.append("invalid signed packet bytes")
    import ast
    try:
        failed_index=ast.literal_eval(receipt.get("negative_error",""))["InstructionError"][0]
    except (ValueError,TypeError,KeyError,IndexError,SyntaxError,AttributeError):
        failed_index=None
    if type(failed_index)is not int or failed_index!=2 or (
            receipt.get("negative_failure_instruction_index") is not None and
            receipt["negative_failure_instruction_index"]!=2):
        errors.append("negative control must fail at final instruction")
    pools=receipt.get("route_pool_addresses")
    if not isinstance(pools,list) or len(pools)!=3 or pools[0]!=pools[2] or not all(isinstance(x,str) and x for x in pools):
        errors.append("authenticated three-hop pools missing")
    mints=receipt.get("route_mints")
    if not isinstance(mints,list) or len(mints)!=4 or mints[0]!=mints[2] or mints[1]!=mints[3] or mints[0]==mints[1]:
        errors.append("open-path three-hop token continuity missing")
    return {"route":"__".join(route),"status":"VERIFIED_THREE_HOP_SIGNED_OFFLINE" if not errors else "UNVERIFIED",
            "failure_reasons":errors,**SAFE}

def audit(root):
    rows=[]
    for route in PAIRS:
        path=Path(root)/("__".join(route)+".json")
        if not path.is_file():
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["signed three-hop receipt missing"],**SAFE})
            continue
        try:rows.append(assess(route,json.loads(path.read_text())))
        except (ValueError,TypeError,OSError,KeyError) as exc:
            rows.append({"route":"__".join(route),"status":"UNVERIFIED",
                         "failure_reasons":["invalid receipt: "+str(exc)[:160]],**SAFE})
    verified=sum(x["status"]=="VERIFIED_THREE_HOP_SIGNED_OFFLINE" for x in rows)
    return {"status":"INDEPENDENT_SIGNED_THREE_HOP_ACCEPTANCE",
            "verified":verified,"target":2,"routes":rows,
            "four_to_six_hop_verified":False,
            "independently_validated_quote_samples":0,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    result=audit(a.receipts)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"three_hop_verified":result["verified"],"target":2,**SAFE}))
    return 0 if result["verified"]==2 else 1
if __name__=="__main__":raise SystemExit(main())
