"""CI readiness gate: require actual verified liquidity pools for swap-stage work.

This is a separate strict job, not a replacement for program/RPC smoke tests.
"""
import json
import os
import sys

def inspect(report, minimum=1):
    if not isinstance(report, dict):
        raise ValueError("invalid verification report")
    status=report.get("status")
    count=report.get("verifiedPools")
    if status not in ("PASS","NOT_CONFIGURED","FAIL") or type(count) is not int or count < 0:
        raise ValueError("invalid report fields")
    if status == "PASS" and count >= minimum:
        return {"ready":True,"verifiedPools":count}
    return {"ready":False,"verifiedPools":count,"reason":status}

def main():
    path=os.environ.get("POOL_VERIFICATION_REPORT","whirlpool-report.json")
    with open(path,encoding="utf-8") as f:
        result=inspect(json.load(f))
    print(json.dumps(result,indent=2))
    return 0 if result["ready"] else 1

if __name__=="__main__":
    sys.exit(main())
