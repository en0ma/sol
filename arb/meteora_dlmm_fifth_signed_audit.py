"""Independent DLMM signed V1 exact-input audit on original SPL post-state bytes.

No RPC or program simulation. Re-decodes the transaction's signed message
and two Solana SPL token accounts, verifies native/SDK pricing from captured
same-slot account bytes, rejects duplicate directions/sizes/signatures.
No registry writes or broadcasting.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.transaction import VersionedTransaction
from arb.meteora_dlmm import PROGRAM
from arb.meteora_dlmm_swap import SWAP_DISCRIMINATOR
from arb.meteora_dlmm_native_candidate_audit import calculate
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

SAFE={"actionable":False,"broadcast":False,
      "live_execution_approved":False,"registry_admission_approved":False}


def audit(source,sdk,signed):
    native=calculate(source,sdk)
    if (not isinstance(signed,dict) or signed.get("venue")!="meteora_dlmm"
            or signed.get("status")!="DLMM_REAL_SIGNED_SDK_NATIVE_SPL_PARITY"
            or signed.get("signed_parity_verified") is not True
            or any(signed.get(k) is not False for k in SAFE)):
        raise ValueError("DLMM signed evidence missing or untrusted")
    digest=signed.get("dlmm_program_elf_sha256")
    if (not isinstance(digest,str) or len(digest)!=64 or
            any(c not in "0123456789abcdef" for c in digest)):
        raise ValueError("DLMM authentic ELF digest missing")
    entries=signed.get("pools")
    if not isinstance(entries,list) or len(entries)!=native["verified_pools"]:
        raise ValueError("DLMM independent signed pool count mismatch")
    native_pools={p["pool"]:p for p in native["pools"]}
    if len(native_pools)!=len(entries) or len({p.get("pool") for p in entries})!=len(entries):
        raise ValueError("DLMM signed pool duplication")
    audited=[]
    for entry in entries:
        address=entry.get("pool")
        reference=native_pools.get(address)
        if (not isinstance(reference,dict) or entry.get("verified") is not True
                or entry.get("source_slot")!=reference["source_slot"]
                or entry.get("source_sha256")!=reference["source_sha256"]):
            raise ValueError("DLMM source authenticated pool mismatch")
        rows=entry.get("trials")
        if not isinstance(rows,list) or len(rows)!=4:
            raise ValueError("DLMM four genuine signed trials required")
        quotes={(r["mint_in"],r["amount_in"]):r for r in reference["trials"]}
        seen=set()
        signatures=set()
        for item in rows:
            if not isinstance(item,dict) or item.get("pool")!=address or (
                    item.get("status")!="SIGNED_DLMM_SDK_NATIVE_SPL_EXACT"):
                raise ValueError("DLMM signed trial identity invalid")
            mint=item.get("input_mint")
            amount=item.get("amount_in")
            if not isinstance(mint,str) or type(amount) is not int or not 0<amount<2**64:
                raise ValueError("DLMM signed trial input not integer")
            key=(mint,amount)
            if key in seen or key not in quotes:
                raise ValueError("DLMM duplicate/unreferenced signed trial")
            seen.add(key)
            ref=quotes[key]
            if (item.get("direction")!=ref["direction"] or
                    item.get("output_mint")!=ref["mint_out"] or
                    item.get("signed_output")!=ref["native_integer_output"] or
                    item.get("official_sdk_output")!=ref["native_integer_output"] or
                    item.get("native_integer_output")!=ref["native_integer_output"] or
                    item.get("source_slot")!=reference["source_slot"] or
                    item.get("source_sha256")!=reference["source_sha256"]):
                raise ValueError("DLMM signed SPL/native/SDK output or source mismatch")
            encoded=item.get("signed_transaction_base64")
            if not isinstance(encoded,str):
                raise ValueError("DLMM signed transaction bytes missing")
            signed_data=base64.b64decode(encoded,validate=True)
            if base64.b64encode(signed_data).decode()!=encoded or not signed_data:
                raise ValueError("DLMM signed transaction bytes noncanonical")
            tx=VersionedTransaction.from_bytes(signed_data)
            tx.verify_and_hash_message()
            if (len(tx.message.instructions)!=1 or
                    item.get("signed_sha256")!=hashlib.sha256(signed_data).hexdigest() or
                    not tx.signatures or
                    item.get("signed_signature")!=str(tx.signatures[0]) or
                    str(tx.signatures[0]) in signatures):
                raise ValueError("DLMM signed transaction or signature invalid")
            signatures.add(str(tx.signatures[0]))
            instruction=tx.message.instructions[0]
            keys=[str(k) for k in tx.message.account_keys]
            if keys[instruction.program_id_index]!=PROGRAM:
                raise ValueError("DLMM signed instruction did not invoke program")
            indexes=list(instruction.accounts)
            if len(indexes)<16 or any(i>=len(keys) for i in indexes):
                raise ValueError("DLMM signed swap account inventory invalid")
            accounts=[keys[i] for i in indexes]
            if (accounts[0]!=address or
                    accounts[4]!=item.get("input_token_account") or
                    accounts[5]!=item.get("output_token_account") or
                    accounts[10] not in keys[:tx.message.header.num_required_signatures]
                    or accounts[11]!=TOKEN_PROGRAM or accounts[12]!=TOKEN_PROGRAM):
                raise ValueError("DLMM signed pool, user and SPL roles mismatch")
            in_mint,out_mint=(accounts[6],accounts[7]) if item["direction"]=="x_to_y" else (accounts[7],accounts[6])
            if (in_mint,out_mint)!=(mint,item["output_mint"]):
                raise ValueError("DLMM signed swap mint direction mismatch")
            data=bytes(instruction.data)
            if (len(data)!=24 or data[:8]!=SWAP_DISCRIMINATOR or
                    int.from_bytes(data[8:16],"little")!=amount or
                    int.from_bytes(data[16:24],"little")!=ref["native_integer_output"]):
                raise ValueError("DLMM signed exact-input data and minimum mismatch")
            post=item.get("post_spl_account_data_base64")
            if not isinstance(post,list) or len(post)!=2:
                raise ValueError("DLMM post-simulation SPL inventory missing")
            out=[]
            for encoded_account,mint_expected in zip(post,(in_mint,out_mint)):
                if not isinstance(encoded_account,str):
                    raise ValueError("DLMM SPL post-account invalid")
                account_data=base64.b64decode(encoded_account,validate=True)
                spl=decode_token_account(account_data)
                if spl["mint"]!=mint_expected or spl["authority"]!=accounts[10]:
                    raise ValueError("DLMM simulated SPL mint or owner differs")
                out.append(spl["amount_base_units"])
            if out!=[0,ref["native_integer_output"]]:
                raise ValueError("DLMM independently decoded SPL debit/output disagrees")
            logs=item.get("simulation_logs")
            if (not isinstance(logs,list) or not all(isinstance(l,str) for l in logs)
                    or not any("Program "+PROGRAM+" invoke" in l for l in logs)
                    or not any("Program "+PROGRAM+" success" in l for l in logs)):
                raise ValueError("DLMM signed program success logs missing")
        if set(quotes)!=seen or len(signatures)!=4:
            raise ValueError("DLMM four unique signed directions/sizes not independently audited")
        audited.append({"pool":address,"source_sha256":reference["source_sha256"],
            "source_slot":reference["source_slot"],
            "signed_transaction_hashes":[r["signed_sha256"] for r in rows],
            "four_signed_native_sdk_spl_swaps_verified":True})
    return {"venue":"meteora_dlmm",
        "status":"INDEPENDENT_DLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
        "independently_signed_verified_pools":len(audited),
        "pools":audited,"signed_parity_verified":True,
        "independent_signed_audit_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source","sdk","signed","output"):
        p.add_argument("--"+name,required=True)
    args=p.parse_args()
    proof=audit(json.loads(Path(args.source).read_text()),
                json.loads(Path(args.sdk).read_text()),
                json.loads(Path(args.signed).read_text()))
    Path(args.output).write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps({"status":proof["status"],
                      "verified_pools":proof["independently_signed_verified_pools"]}))


if __name__=="__main__":
    main()
