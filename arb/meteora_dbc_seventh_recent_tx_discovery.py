"""Read-only original-chain DBC pool candidate discovery without getProgramAccounts.

Search recent DBC program transactions, then authenticate program-owned 424-byte
VirtualPool accounts among transaction keys in synchronized getMultipleAccounts
reads. Transaction key roles are hints only. No API authority, pricing, signatures
or signed registry admission is inferred.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from arb.rpc import call
from arb.meteora_dbc_seventh_venue_source import (
    PROGRAM, DISC, VIRTUAL_POOL_ACCOUNT_SIZE,
)


def discover(rpc, *, count=3, max_signatures=48):
    if (type(count) is not int or not 1 <= count <= 12
            or type(max_signatures) is not int or not count <= max_signatures <= 64):
        raise ValueError("DBC bounded onchain discovery arguments required")
    signatures=call(rpc,"getSignaturesForAddress",[
        PROGRAM,{"limit":max_signatures,"commitment":"confirmed"}
    ])
    if not isinstance(signatures,list) or len(signatures)>max_signatures:
        raise ValueError("DBC program signatures response malformed")
    found=[]
    seen=set()
    attempts=0
    for entry in signatures:
        if not isinstance(entry,dict) or not isinstance(entry.get("signature"),str):
            continue
        if entry.get("err") is not None:
            continue
        tx=call(rpc,"getTransaction",[entry["signature"],{
            "encoding":"json","commitment":"confirmed",
            "maxSupportedTransactionVersion":0
        }])
        if not isinstance(tx,dict) or not isinstance(tx.get("transaction"),dict):
            continue
        message=tx["transaction"].get("message")
        if not isinstance(message,dict) or not isinstance(message.get("accountKeys"),list):
            continue
        raw_keys=message["accountKeys"]
        loaded=(tx.get("meta") or {}).get("loadedAddresses") or {}
        if not isinstance(loaded,dict):
            continue
        keys=[]
        for candidate in raw_keys+loaded.get("writable",[])+loaded.get("readonly",[]):
            k=candidate.get("pubkey") if isinstance(candidate,dict) else candidate
            if isinstance(k,str) and k not in seen and k!=PROGRAM:
                keys.append(k)
                seen.add(k)
        if len(keys)>128:
            raise ValueError("DBC transaction has excessive keys for research")
        # Batch under the official getMultipleAccounts 100-address limit.
        for start in range(0,len(keys),50):
            chunk=keys[start:start+50]
            if not chunk:continue
            attempts+=1
            response=call(rpc,"getMultipleAccounts",[chunk,{
                "encoding":"base64","commitment":"confirmed"
            }])
            if (not isinstance(response,dict) or
                    not isinstance(response.get("context"),dict) or
                    type(response["context"].get("slot")) is not int or
                    not isinstance(response.get("value"),list) or
                    len(response["value"])!=len(chunk)):
                raise ValueError("DBC onchain discovery context invalid")
            for key,account in zip(chunk,response["value"]):
                if (not isinstance(account,dict) or account.get("owner")!=PROGRAM
                        or account.get("executable") is not False
                        or not isinstance(account.get("data"),list)
                        or len(account["data"])!=2 or account["data"][1]!="base64"):
                    continue
                raw=base64.b64decode(account["data"][0],validate=True)
                if len(raw)!=VIRTUAL_POOL_ACCOUNT_SIZE or raw[:8]!=DISC:
                    continue
                found.append({"address":key,
                    "hint_status":"READONLY_PROGRAM_OWNER_AND_VIRTUAL_POOL_SHAPE_CHECKED",
                    "discovery_slot":response["context"]["slot"],
                    "source_sha256":hashlib.sha256(raw).hexdigest()})
                if len(found)>=count:
                    break
            if len(found)>=count:break
        if len(found)>=count:break
    return {"venue":"meteora_dbc",
      "status":"ONCHAIN_TRANSACTION_HINTS_REQUIRE_FRESH_SOURCE_VALIDATION",
      "program":PROGRAM,"program_transactions_checked":len(signatures),
      "account_batches_checked":attempts,"hints":found,
      "authenticated_pricing_pools":0,"signed_verified_pools":0,
      "actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--count",type=int,default=6)
    p.add_argument("--max-signatures",type=int,default=48)
    p.add_argument("--output",required=True)
    a=p.parse_args()
    r=discover(a.rpc,count=a.count,max_signatures=a.max_signatures)
    Path(a.output).write_text(json.dumps(r,indent=2)+"\n")
    print(json.dumps({"hints":len(r["hints"]),
                      "program_transactions_checked":r["program_transactions_checked"],
                      "signed_verified_pools":0}))
    if len(r["hints"])<a.count:
        raise SystemExit("DBC onchain transaction identity discovery incomplete")


if __name__=="__main__":
    main()
