"""PumpSwap real signed Surfpool parity runner, no signing keys or broadcasting.

Accepts pre-signed transaction bytes, obtains local pre-simulation token balances,
and runs four independent sig-verified Solana simulations. Untrusted manifest
amounts/outputs are never accepted as simulation proof. This runner never
creates a signature and cannot admit a pool without a separate receipt audit.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path

from arb.pumpswap_local_simulation import local_rpc_only, simulate_signed
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

SAFE={"actionable":False,"broadcast":False,"registry_admission_approved":False}


def balance(rpc, address, mint):
    result=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
    account=result.get("value")
    if (not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM or
            account.get("executable") is not False or
            account.get("data",[None,None])[1]!="base64"):
        raise ValueError("signed trial token account unavailable")
    token=decode_token_account(base64.b64decode(account["data"][0],validate=True))
    if token["mint"]!=mint:
        raise ValueError("signed trial token mint identity mismatch")
    return token["amount_base_units"]


def run(rpc, sdk_report, manifest):
    local_rpc_only(rpc)
    if (not isinstance(sdk_report,dict) or sdk_report.get("venue")!="pumpswap"
            or not isinstance(sdk_report.get("pools"),list)
            or not isinstance(manifest,dict) or manifest.get("venue")!="pumpswap"
            or not isinstance(manifest.get("trials"),list)):
        raise ValueError("PumpSwap SDK comparison and signed manifest required")
    sdk_pools={p.get("address"):p for p in sdk_report["pools"] if isinstance(p,dict)}
    if len(sdk_pools)!=len(sdk_report["pools"]):
        raise ValueError("duplicate SDK pool")
    entries={}
    for item in manifest["trials"]:
        if not isinstance(item,dict):
            raise ValueError("malformed signed trial manifest")
        pool=item.get("pool")
        mint=item.get("input_mint")
        size=item.get("amount_in")
        if (not isinstance(pool,str) or not isinstance(mint,str)
                or type(size) is not int or size<=0):
            raise ValueError("invalid signed trial identity")
        key=(pool,mint,size)
        if key in entries:
            raise ValueError("duplicate signed trial identity")
        entries[key]=item
    # Enforce complete trial identity coverage before parsing any transaction
    # or touching Surfpool. A malformed transaction in an otherwise incomplete
    # manifest must never mask the missing-trial error.
    expected_keys=set()
    for pool, comparison in sdk_pools.items():
        references=comparison.get("trials")
        if not isinstance(references,list) or len(references)!=4:
            raise ValueError("four official SDK comparisons required")
        for quote in references:
            key=(pool,quote.get("input_mint"),quote.get("amount_in"))
            if (not isinstance(key[1],str) or type(key[2]) is not int
                    or key[2]<=0 or key in expected_keys):
                raise ValueError("invalid or duplicate official SDK trial identity")
            expected_keys.add(key)
    if set(entries)!=expected_keys:
        raise ValueError("missing or unexpected signed trial for SDK quote")
    results=[]
    for pool, comparison in sdk_pools.items():
        reference=comparison.get("trials")
        if not isinstance(reference,list) or len(reference)!=4:
            raise ValueError("four official SDK comparisons required")
        proofs=[]
        seen=set()
        for quote in reference:
            mint=quote.get("input_mint")
            size=quote.get("amount_in")
            key=(pool,mint,size)
            if (not isinstance(mint,str) or type(size) is not int or
                    size<=0 or key in seen or key not in entries):
                raise ValueError("missing or duplicate signed trial for SDK quote")
            seen.add(key)
            if quote.get("status")!="OFFICIAL_SDK_CANDIDATE_EXACT":
                raise ValueError("official SDK did not verify native price")
            expected=int(quote["official_sdk_output"])
            if expected<=0 or str(expected)!=quote.get("python_candidate_output"):
                raise ValueError("SDK/native candidate output mismatch")
            item=entries[key]
            if (item.get("source_slot")!=comparison.get("source_slot") or
                    item.get("source_digest")!=comparison.get("source_digest")):
                raise ValueError("signed trial source identity mismatch")
            input_address=item.get("input_token_account")
            output_address=item.get("output_token_account")
            output_mint=item.get("output_mint")
            signed_b64=item.get("signed_transaction_base64")
            if any(not isinstance(x,str) or not x for x in (
                    input_address,output_address,output_mint,signed_b64)):
                raise ValueError("signed trial accounts or signed transaction unavailable")
            signed_bytes=base64.b64decode(signed_b64,validate=True)
            if not signed_bytes or base64.b64encode(signed_bytes).decode()!=signed_b64:
                raise ValueError("invalid signed transaction bytes")
            from solders.transaction import VersionedTransaction
            transaction=VersionedTransaction.from_bytes(signed_bytes)
            transaction.verify_and_hash_message()
            before_in=balance(rpc,input_address,mint)
            before_out=balance(rpc,output_address,output_mint)
            result=simulate_signed(rpc,signed_bytes,input_address,output_address,
                mint,output_mint,before_in,before_out,size,min_amount_out=expected)
            if result["received_base_units"]!=expected:
                raise ValueError("signed SPL output differs from native and SDK")
            if result["spent_base_units"]!=size:
                raise ValueError("signed exact-input debit differs from quoted amount")
            proofs.append({"pool":pool,"input_mint":mint,"output_mint":output_mint,
                "amount_in":size,"signed_spl_output":result["received_base_units"],
                "official_sdk_output":expected,"native_output":expected,
                "signed_sha256":hashlib.sha256(signed_bytes).hexdigest(),
                "status":"PUMPSWAP_SIGNED_SDK_NATIVE_EXACT"})
        if len({x["input_mint"] for x in proofs})!=2 or any(
                sum(x["input_mint"]==m for x in proofs)!=2
                for m in {x["input_mint"] for x in proofs}):
            raise ValueError("signed parity requires two directions with two sizes")
        results.append({"pool":pool,"trials":proofs,"verified":True})
    if len(entries)!=sum(len(x["trials"]) for x in results):
        raise ValueError("unrecognized additional signed trial manifest entries")
    return {"venue":"pumpswap","status":"PUMPSWAP_SIGNED_SDK_NATIVE_EXACT",
        "pools":results,"signed_parity_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rpc",required=True)
    p.add_argument("--sdk-report",required=True)
    p.add_argument("--signed-manifest",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=run(args.rpc,json.loads(Path(args.sdk_report).read_text()),
               json.loads(Path(args.signed_manifest).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":len(result["pools"])}))


if __name__=="__main__":
    main()
