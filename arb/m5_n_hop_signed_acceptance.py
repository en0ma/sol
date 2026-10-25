"""Strict independent signed offline four-to-six-hop evidence acceptance."""
import argparse
import json
from pathlib import Path
from arb.m5_three_hop_signed_acceptance import SAFE,PAIRS

def assess(pair,n,r):
    reasons=[]
    expected=[pair[i%2] for i in range(n)]
    for key,value in (("legs",n),("route_venues",expected),
                      ("status","SIGNED_N_LEG_ATOMIC_AND_ROLLBACK_VERIFIED"),
                      ("execution_environment","ISOLATED_SURFPOOL_OFFLINE"),
                      ("quote_accuracy_verified",False),
                      ("signed_cpi_per_leg_verified",True),
                      ("rollback_failure_case_verified",True),
                      ("signed_atomic_simulation_verified",True)):
        if r.get(key)!=value:reasons.append("incorrect "+key)
    for key,value in SAFE.items():
        if r.get(key) is not value:reasons.append("unsafe "+key)
    if r.get("source_snapshot_slot") is not None:reasons.append("unsubstantiated source slot")
    inputs=r.get("planned_inputs")
    if not isinstance(inputs,list) or len(inputs)!=n or any(type(a)is not int or not 0<a<2**64 for a in inputs):
        reasons.append("invalid planned exact inputs")
    hops=r.get("cpi_hops")
    if not isinstance(hops,list) or len(hops)!=n-1:
        reasons.append("incorrect N-1 signed CPI hops")
    elif isinstance(inputs,list) and len(inputs)==n:
        for index,hop in enumerate(hops,1):
            if (not isinstance(hop,dict) or hop.get("hop")!=index
                    or not isinstance(hop.get("account"),str) or not hop.get("account")
                    or any(hop.get(key)!=inputs[index] for key in
                           ("planned_input_base_units","received_base_units","consumed_base_units"))):
                reasons.append("CPI continuity hop "+str(index))
    post=r.get("positive_post_balances_base_units")
    if (not isinstance(post,list) or len(post)!=n+1 or
            any(type(a)is not int or a!=0 for a in post[:-1]) or
            type(post[-1]) is not int or post[-1]<=0):
        reasons.append("signed SPL terminal or intermediate balances")
    pools=r.get("route_pool_addresses")
    if not isinstance(pools,list) or len(pools)!=n or pools!=[pools[i%2] for i in range(n)] or any(not isinstance(p,str) or not p for p in pools):
        reasons.append("authenticated alternating pool identities")
    mints=r.get("route_mints")
    if (not isinstance(mints,list) or len(mints)!=n+1 or
            any(not isinstance(m,str) or not m for m in mints) or
            any(mints[i]!=mints[i%2] for i in range(n+1)) or mints[0]==mints[1]):
        reasons.append("connected two-mint route identity")
    size=r.get("signed_packet_bytes")
    if type(size)is not int or not 100<=size<=1232:reasons.append("signed packet size")
    if "InstructionError" not in str(r.get("negative_error","")):
        reasons.append("missing negative last-leg instruction error")
    return {"route":"__".join(pair),"legs":n,
            "status":"VERIFIED_SIGNED_N_HOP" if not reasons else "UNVERIFIED",
            "failure_reasons":reasons,**SAFE}

def audit(root):
    rows=[]
    for n in (4,5,6):
        for pair in PAIRS:
            name="__".join(pair)
            file=Path(root)/f"amm-v4-{n}-hop"/(name+".json")
            try:
                receipt=json.loads(file.read_text())
                rows.append(assess(pair,n,receipt))
            except (OSError,ValueError,TypeError) as exc:
                rows.append({"route":name,"legs":n,"status":"UNVERIFIED",
                             "failure_reasons":[str(exc)[:160]],**SAFE})
    verified=sum(r["status"]=="VERIFIED_SIGNED_N_HOP" for r in rows)
    return {"status":"SIGNED_4_TO_6_HOP_INDEPENDENT_ACCEPTANCE",
            "verified":verified,"target":6,"routes":rows,
            "independently_validated_quote_samples":0,**SAFE}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipts",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    a=p.parse_args()
    result=audit(a.receipts)
    a.output.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"verified":result["verified"],"target":6,**SAFE}))
    return 0 if result["verified"]==6 else 1
if __name__=="__main__":raise SystemExit(main())
