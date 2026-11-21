"""Independent post-hoc PumpSwap V2 signed execution receipt auditor.

Reconstructs four on-chain program instruction intents, verifies Ed25519
transaction signatures and SPL post-state amounts from raw recorded bytes,
and checks the independent SDK/native candidate reference per pool.
Never contacts RPC, signs, broadcasts, or mutates any registry.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from solders.transaction import VersionedTransaction

from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_sdk_candidate_audit import audit as sdk_audit
from arb.pumpswap_signed_parity import verify_transaction_intent
from arb.token_vaults import decode_token_account

SAFE={"actionable":False,"broadcast":False,"registry_admission_approved":False}


def audit(source,sdk,result):
    sdk_audit(source,sdk)
    if (not isinstance(result,dict) or result.get("venue")!="pumpswap"
            or result.get("status")!="SIGNED_PUMPSWAP_ISOLATED_PARITY"
            or any(result.get(k) is not False for k in SAFE)):
        raise ValueError("signed PumpSwap proof absent or unsafe")
    proof=result.get("signed_proof")
    if (not isinstance(proof,dict) or proof.get("venue")!="pumpswap"
            or proof.get("status")!="PUMPSWAP_SIGNED_SDK_NATIVE_EXACT"
            or proof.get("signed_parity_verified") is not True
            or any(proof.get(k) is not False for k in SAFE)):
        raise ValueError("missing signed execution receipt")
    program_hashes=result.get("program_elf_sha256")
    from arb.pumpswap_fee_account import PROGRAM as FEE_PROGRAM
    if (not isinstance(program_hashes,dict) or set(program_hashes)!={PROGRAM,FEE_PROGRAM}
            or any(not isinstance(x,str) or len(x)!=64 or
                   any(c not in "0123456789abcdef" for c in x)
                   for x in program_hashes.values())):
        raise ValueError("missing authenticated PumpSwap and fee program ELF digests")
    entries=proof.get("pools")
    sdk_pools=sdk.get("pools")
    if not isinstance(entries,list) or not isinstance(sdk_pools,list):
        raise ValueError("signed pool receipt list missing")
    indexed={row.get("pool"):row for row in entries if isinstance(row,dict)}
    references={row.get("address"):row for row in sdk_pools if isinstance(row,dict)}
    if (len(indexed)!=len(entries) or len(references)!=len(sdk_pools)
            or set(indexed)!=set(references) or not indexed):
        raise ValueError("signed and SDK pool identities mismatch")
    independently_audited=[]
    for address,reference in references.items():
        entry=indexed[address]
        if entry.get("verified") is not True:
            raise ValueError("pool signed verified marker missing")
        observed=entry.get("trials")
        quotes=reference.get("trials")
        if not isinstance(observed,list) or len(observed)!=4 or (
                not isinstance(quotes,list) or len(quotes)!=4):
            raise ValueError("four signed and SDK trials required per pool")
        by_key={(q.get("input_mint"),q.get("amount_in")):q for q in quotes}
        if len(by_key)!=4:
            raise ValueError("duplicate SDK trial identities")
        seen=set()
        signature_set=set()
        for receipt in observed:
            if not isinstance(receipt,dict) or receipt.get("pool")!=address or (
                    receipt.get("status")!="PUMPSWAP_SIGNED_SDK_NATIVE_EXACT"):
                raise ValueError("invalid signed trial receipt")
            mint=receipt.get("input_mint")
            size=receipt.get("amount_in")
            if not isinstance(mint,str) or type(size) is not int or size<=0:
                raise ValueError("invalid signed trial input")
            key=(mint,size)
            if key in seen or key not in by_key:
                raise ValueError("duplicate or unexpected signed trial identity")
            seen.add(key)
            quote=by_key[key]
            expected=int(quote["official_sdk_output"])
            if (quote.get("status")!="OFFICIAL_SDK_CANDIDATE_EXACT" or
                    str(expected)!=quote["python_candidate_output"] or
                    receipt.get("official_sdk_output")!=expected or
                    receipt.get("native_output")!=expected or
                    receipt.get("signed_spl_output")!=expected):
                raise ValueError("signed output does not match independent native and SDK")
            if (receipt.get("source_slot")!=reference["source_slot"] or
                    receipt.get("source_digest")!=reference["source_digest"]):
                raise ValueError("signed receipt did not preserve authenticated snapshot")
            output_mint=receipt.get("output_mint")
            input_account=receipt.get("input_token_account")
            output_account=receipt.get("output_token_account")
            if any(not isinstance(x,str) or not x for x in (
                    output_mint,input_account,output_account)):
                raise ValueError("signed SPL role identity missing")
            encoded=receipt.get("signed_transaction_base64")
            if not isinstance(encoded,str):
                raise ValueError("signed transaction bytes absent")
            signed=base64.b64decode(encoded,validate=True)
            if base64.b64encode(signed).decode()!=encoded or not signed:
                raise ValueError("signed transaction noncanonical")
            if receipt.get("signed_sha256")!=hashlib.sha256(signed).hexdigest():
                raise ValueError("signed transaction content hash disagreement")
            tx=VersionedTransaction.from_bytes(signed)
            tx.verify_and_hash_message()
            if (not tx.signatures or
                    receipt.get("signed_signature")!=str(tx.signatures[0])
                    or receipt["signed_signature"] in signature_set):
                raise ValueError("signed signature missing or repeated")
            signature_set.add(receipt["signed_signature"])
            verify_transaction_intent(tx,address,mint,output_mint,
                input_account,output_account,size,expected)
            before_in=receipt.get("initial_input_base_units")
            before_out=receipt.get("initial_output_base_units")
            if (type(before_in) is not int or type(before_out) is not int
                    or before_in<size or before_out<0):
                raise ValueError("untrusted initial SPL token account balances")
            post=receipt.get("post_spl_account_data_base64")
            if not isinstance(post,list) or len(post)!=2:
                raise ValueError("signed post-state SPL evidence missing")
            amounts=[]
            # Compare the owner/mint in the raw SPL bytes to the signed
            # instruction user; a mere price-like output isn't proof.
            from arb.pumpswap_trade_v2 import ORDER
            ix=tx.message.instructions[0]
            keys=[str(k) for k in tx.message.account_keys]
            user=keys[ix.accounts[ORDER.index("user")]]
            for data,m in zip(post,(mint,output_mint)):
                if not isinstance(data,str):
                    raise ValueError("invalid signed SPL raw bytes")
                raw=base64.b64decode(data,validate=True)
                if base64.b64encode(raw).decode()!=data:
                    raise ValueError("signed SPL base64 noncanonical")
                token=decode_token_account(raw)
                if token["mint"]!=m or token["authority"]!=user:
                    raise ValueError("signed SPL account mint or signer authority mismatch")
                amounts.append(token["amount_base_units"])
            if before_in-amounts[0]!=size or amounts[1]-before_out!=expected:
                raise ValueError("independently decoded SPL debit/output mismatch")
            logs=receipt.get("simulation_logs")
            if (not isinstance(logs,list) or not all(isinstance(line,str) for line in logs)
                    or not any("Program "+PROGRAM+" invoke" in x for x in logs)
                    or not any("Program "+PROGRAM+" success" in x for x in logs)):
                raise ValueError("signed PumpSwap execution success logs absent")
        if set(by_key)!=seen or len(signature_set)!=4:
            raise ValueError("missing unique signed four-trial execution")
        directions={q["input_mint"] for q in quotes}
        if len(directions)!=2 or any(sum(k[0]==m for k in seen)!=2 for m in directions):
            raise ValueError("signed directions or distinct amounts incomplete")
        independently_audited.append({"pool":address,
            "source_slot":reference["source_slot"],
            "source_digest":reference["source_digest"],
            "four_genuine_signed_trials_audited":True,
            "signed_transaction_hashes":[r["signed_sha256"] for r in observed]})
    return {"venue":"pumpswap","status":"INDEPENDENT_SIGNED_NATIVE_SDK_SPL_PARITY",
        "verified_pools":len(independently_audited),"pools":independently_audited,
        "signed_parity_verified":True,"independent_signed_audit_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source",required=True)
    p.add_argument("--sdk",required=True)
    p.add_argument("--signed",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    result=audit(json.loads(Path(args.source).read_text()),
                 json.loads(Path(args.sdk).read_text()),
                 json.loads(Path(args.signed).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":result["verified_pools"]}))


if __name__=="__main__":
    main()
