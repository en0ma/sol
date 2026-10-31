"""Independent post-hoc Raydium CLMM signed-native-SDK-SPL receipt auditor.

Recomputes native exact Q64 candidates from the immutable authenticated
snapshot, binds the official SDK output to the same pool+slot digest, verifies
genuine Ed25519 signature and exact SwapV2 instruction account/amount/price
intent, then independently decodes raw SPL post-state. No RPC, keys,
simulations, registry mutation or mainnet broadcasting in this module.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.transaction import VersionedTransaction
from arb.raydium_clmm import PROGRAM
from arb.raydium_clmm_swap import DISC
from arb.raydium_clmm_native_single_tick import evaluate
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

SAFE={"actionable":False,"broadcast":False,
      "live_execution_approved":False,"registry_admission_approved":False}


def audit(tick_source,sdk,signed):
    native=evaluate(tick_source)
    if (not isinstance(signed,dict) or signed.get("venue")!="raydium_clmm"
            or signed.get("status")!="SIGNED_RAYDIUM_CLMM_NATIVE_SDK_SPL_PARITY"
            or signed.get("signed_parity_verified") is not True
            or any(signed.get(k) is not False for k in SAFE)):
        raise ValueError("Raydium CLMM signed proof missing or unsafe")
    elf=signed.get("program_elf_sha256")
    if not isinstance(elf,str) or len(elf)!=64 or any(c not in "0123456789abcdef" for c in elf):
        raise ValueError("CLMM signed executable ELF provenance absent")
    if (sdk.get("status")!="RAYDIUM_CLMM_NATIVE_SDK_SINGLE_TICK_EXACT"
            or sdk.get("official_sdk_native_parity_verified") is not True):
        raise ValueError("CLMM independent official SDK price reference missing")
    source_by_pool={r["pool"]:r for r in tick_source["pools"]}
    native_by_pool={r["pool"]:r for r in native["pools"]}
    sdk_by_pool={r["pool"]:r for r in sdk["pools"]}
    signed_pools=signed.get("pools")
    if (not isinstance(signed_pools,list) or len(signed_pools)!=len(source_by_pool)
            or len(set(x.get("pool") for x in signed_pools))!=len(signed_pools)
            or set(sdk_by_pool)!=set(native_by_pool)
            or set(sdk_by_pool)!=set(source_by_pool)):
        raise ValueError("CLMM missing or duplicate independent signed pool identities")
    accepted=[]
    for pool in signed_pools:
        address=pool["pool"]
        captured=source_by_pool.get(address)
        quote_pool=sdk_by_pool.get(address)
        native_pool=native_by_pool.get(address)
        if (not captured or not quote_pool or not native_pool
            or pool.get("verified") is not True
            or pool.get("source_slot")!=captured["tick_capture"]["tick_array_source_slot"]
            or pool.get("tick_snapshot_sha256")!=captured["tick_snapshot_sha256"]
            or quote_pool["tick_snapshot_sha256"]!=captured["tick_snapshot_sha256"]
            or native_pool["snapshot_sha256"]!=captured["tick_snapshot_sha256"]):
            raise ValueError("CLMM signed source identity or slot mismatch")
        native_refs={(q["zero_for_one"],q["amount_in"]):q
                     for q in native_pool["quotes"]}
        sdk_refs={(q["zero_for_one"],q["amount_in"]):q
                  for q in quote_pool["trials"]}
        rows=pool.get("trials")
        if (not isinstance(rows,list) or len(rows)!=4 or len(native_refs)!=4
            or len(sdk_refs)!=4):
            raise ValueError("four CLMM signed and official price quotes required")
        seen=set();signatures=set()
        for entry in rows:
            if (not isinstance(entry,dict) or
                entry.get("status")!="SIGNED_RAYDIUM_CLMM_NATIVE_SDK_SPL_EXACT"
                or entry.get("pool")!=address):
                raise ValueError("CLMM signed trial status/pool invalid")
            direction=entry.get("zero_for_one")
            amount=entry.get("amount_in")
            if type(direction) is not bool or type(amount) is not int or amount<=0:
                raise ValueError("CLMM signed direction and native amount invalid")
            key=(direction,amount)
            if key in seen or key not in native_refs or key not in sdk_refs:
                raise ValueError("CLMM duplicate or extra signed trial identity")
            seen.add(key)
            ref=sdk_refs[key];native_ref=native_refs[key]
            output=native_ref["output"]
            if (ref.get("status")!="OFFICIAL_SDK_NATIVE_SINGLE_TICK_EXACT"
                or ref.get("all_trade") is not True
                or int(ref.get("official_sdk_output","-1"))!=output
                or int(ref.get("official_fee","-1"))!=native_ref["fee"]
                or any(entry.get(k)!=output for k in (
                    "official_sdk_output","native_integer_output","signed_spl_output"))
                or entry.get("source_slot")!=pool["source_slot"]
                or entry.get("tick_snapshot_sha256")!=pool["tick_snapshot_sha256"]):
                raise ValueError("CLMM signed amount, source or SDK/native discrepancy")
            encoded=entry.get("signed_transaction_base64")
            if not isinstance(encoded,str):
                raise ValueError("CLMM signed wire bytes absent")
            raw=base64.b64decode(encoded,validate=True)
            if not raw or base64.b64encode(raw).decode()!=encoded:
                raise ValueError("CLMM signed wire data noncanonical")
            tx=VersionedTransaction.from_bytes(raw)
            tx.verify_and_hash_message()
            if (not tx.signatures or entry.get("signed_sha256")!=hashlib.sha256(raw).hexdigest()
                or entry.get("signed_signature")!=str(tx.signatures[0])
                or entry["signed_signature"] in signatures):
                raise ValueError("CLMM signed hash/signature tampering or repetition")
            signatures.add(entry["signed_signature"])
            message=tx.message
            if len(message.instructions)!=1:
                raise ValueError("CLMM signed transaction contains unrelated instructions")
            ix=message.instructions[0]
            keys=[str(k) for k in message.account_keys]
            if ix.program_id_index>=len(keys) or keys[ix.program_id_index]!=PROGRAM:
                raise ValueError("CLMM signed program is not Raydium CLMM")
            refs=list(ix.accounts)
            if len(refs)<14 or any(i>=len(keys) for i in refs):
                raise ValueError("CLMM signed SwapV2 account inventory invalid")
            roles=[keys[i] for i in refs]
            if (roles[2]!=address or roles[0] not in
                keys[:message.header.num_required_signatures] or
                roles[3]!=entry.get("input_token_account")
                or roles[4]!=entry.get("output_token_account")
                or roles[8]!=TOKEN_PROGRAM or
                roles[11]!=entry.get("input_mint")
                or roles[12]!=entry.get("output_mint")
                or roles[13:]!=([captured["tick_capture"]["bitmap_extension"]["address"]] + ref.get("remaining_tick_arrays")
                    if captured["tick_capture"].get("bitmap_extension",{}).get("present") is True
                    else ref.get("remaining_tick_arrays"))):
                raise ValueError("CLMM signed pool, mint, authority or tick path mismatch")
            data=bytes(ix.data)
            if (len(data)!=41 or data[:8]!=DISC
                or int.from_bytes(data[8:16],"little")!=amount
                or int.from_bytes(data[16:24],"little")!=output
                or int.from_bytes(data[24:40],"little")!=0
                or data[40]!=1):
                raise ValueError("CLMM signed V2 exact amount/threshold/price mismatch")
            values=entry.get("post_spl_account_data_base64")
            if not isinstance(values,list) or len(values)!=2:
                raise ValueError("CLMM poststate SPL account bytes missing")
            balances=[]
            for encoded_account,mint in zip(values,(roles[11],roles[12])):
                if not isinstance(encoded_account,str):
                    raise ValueError("CLMM SPL poststate base64 invalid")
                buf=base64.b64decode(encoded_account,validate=True)
                if base64.b64encode(buf).decode()!=encoded_account:
                    raise ValueError("CLMM SPL poststate bytes noncanonical")
                spl=decode_token_account(buf)
                if spl["mint"]!=mint or spl["authority"]!=roles[0]:
                    raise ValueError("CLMM SPL poststate mint or signer identity invalid")
                balances.append(spl["amount_base_units"])
            if balances!=[0,output]:
                raise ValueError("CLMM independent SPL debit/credit differs from verified output")
            logs=entry.get("simulation_logs")
            if (not isinstance(logs,list) or
                not any("Program "+PROGRAM+" invoke" in t for t in logs)
                or not any("Program "+PROGRAM+" success" in t for t in logs)):
                raise ValueError("CLMM successful on-chain signed simulation logs missing")
        if set(native_refs)!=seen or len(signatures)!=4:
            raise ValueError("CLMM four distinct signed pool trials incomplete")
        accepted.append({"pool":address,"source_slot":pool["source_slot"],
            "source_digest":pool["tick_snapshot_sha256"],
            "four_genuine_signed_swaps_verified":True,
            "signed_transaction_hashes":[r["signed_sha256"] for r in rows]})
    return {"venue":"raydium_clmm",
        "status":"INDEPENDENT_CLMM_SIGNED_NATIVE_SDK_SPL_PARITY",
        "verified_pools":len(accepted),"pools":accepted,
        "independent_signed_audit_verified":True,
        "signed_parity_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("tick-source","sdk","signed","output"):
        p.add_argument("--"+name,required=True)
    args=p.parse_args()
    result=audit(json.loads(Path(args.tick_source).read_text()),
        json.loads(Path(args.sdk).read_text()),
        json.loads(Path(args.signed).read_text()))
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":result["verified_pools"]}))
if __name__=="__main__":main()
