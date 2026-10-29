"""Independent original Meteora DBC signed offline SPL auditor (no RPC).

Re-parses Ed25519-signed transaction wire and original Anchor account roles,
requires four separate exact-in simulations per pool, raw 165-byte legacy
SPL poststate deltas and original source-native/SDK fee parity.
No simulation, account mutation or mainnet broadcast in this auditor.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.transaction import VersionedTransaction
from solders.pubkey import Pubkey
from arb.token_vaults import decode_token_account
from arb.meteora_dbc_swap import DISC

PROGRAM="dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN"
AUTHORITY="FhVo3mqL8PW5pH5U2CN4XE33DokiyZnUwuGpH2hmHLuM"
TOKEN_PROGRAM="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"


def audit(source,sdk,native,signed,*,required=1):
    if source.get("status")=="SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY":
        if source.get("independent_audit",{}).get("authenticated_source_pools")!=6:
            raise ValueError("DBC original independent six-source proof missing")
        source=source["source"]
    if (type(required) is not int or not 1<=required<=6
            or source.get("status")!="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED"
            or sdk.get("status")!="DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY"
            or native.get("status")!="INDEPENDENT_DBC_ORIGINAL_NATIVE_FEE_CURVE_SDK_PARITY"
            or native.get("verified_pools")!=required
            or native.get("verified_trials")!=4*required
            or signed.get("status")!="DBC_SIGNED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTED"
            or signed.get("independent_signed_audit_accepted") is not False
            or signed.get("actionable") is not False
            or signed.get("broadcast") is not False):
        raise ValueError("DBC full source/native/SDK and offline signed diagnostic prerequisite absent")
    entries=signed.get("pools",[])
    if not isinstance(entries,list) or len(entries)!=required:
        raise ValueError("DBC four-signature-per-pool count invalid")
    original={p["pool"]:p for p in source["source_pools"]}
    originals={p["pool"]:p for p in native["pools"]}
    sdk_by={p["pool"]:p for p in sdk["pools"]}
    if len(original)!=required or len(originals)!=required or len(sdk_by)!=required:
        raise ValueError("DBC signed source/native/SDK distinct pool count disagreement")
    result=[];global_signatures=set()
    event,_=Pubkey.find_program_address([b"__event_authority"],Pubkey.from_string(PROGRAM))
    for row in entries:
        address=row["pool"]
        if address not in original or address not in originals or address not in sdk_by:
            raise ValueError("DBC signed pool not present in original source")
        source_row=original[address];ref=originals[address]
        fields=source_row["pool_fields"]
        if (row.get("source_slot")!=source_row["source_slot"] or
            ref["source_pool_sha256"]!=source_row["accounts"][address]["sha256"]):
            raise ValueError("DBC source slot/digest mismatch")
        signed_trials=row.get("trials")
        if not isinstance(signed_trials,list) or len(signed_trials)!=4:
            raise ValueError("DBC four genuine signed trials required per pool")
        expected={(p["direction"],p["amount_in"]):p for p in ref["trials"]}
        if len(expected)!=4:
            raise ValueError("DBC duplicate source-native parity trials")
        seen=set();hashes=[]
        for t in signed_trials:
            direction=t["direction"];amount=t["amount_in"]
            ident=(direction,amount)
            if ident not in expected or ident in seen:
                raise ValueError("DBC signed intent duplicates or foreign trial")
            seen.add(ident)
            quoted=expected[ident]
            output=quoted["native_output"]
            if (t.get("pool")!=address or
                t.get("source_slot")!=source_row["source_slot"] or
                t.get("source_pool_sha256")!=ref["source_pool_sha256"] or
                t.get("sdk_expected_output")!=output or
                t.get("observed_output")!=output):
                raise ValueError("DBC signed source/native/SDK output binding incorrect")
            raw=base64.b64decode(t["raw_signed_transaction_base64"],validate=True)
            if hashlib.sha256(raw).hexdigest()!=t["raw_signed_transaction_sha256"]:
                raise ValueError("DBC signed wire hash differs")
            tx=VersionedTransaction.from_bytes(raw)
            tx.verify_and_hash_message()
            if (len(tx.message.instructions)!=1 or not tx.signatures or
                str(tx.signatures[0])!=t.get("signed_signature") or
                str(tx.signatures[0]) in global_signatures):
                raise ValueError("DBC Ed25519 signature/wire unique trial invalid")
            global_signatures.add(str(tx.signatures[0]))
            ix=tx.message.instructions[0]
            keys=[str(k) for k in tx.message.account_keys]
            if keys[ix.program_id_index]!=PROGRAM:
                raise ValueError("DBC signed transaction invoked wrong program")
            roles=[keys[i] for i in ix.accounts]
            if (len(roles)!=15 or roles[0]!=AUTHORITY or
                roles[1]!=fields["config"] or roles[2]!=address or
                roles[3]!=t["input_token_account"] or
                roles[4]!=t["output_token_account"] or
                roles[5]!=fields["base_vault"] or
                roles[6]!=fields["quote_vault"] or
                roles[7]!=fields["base_mint"] or
                roles[8]!=fields["quote_mint"] or
                roles[10]!=TOKEN_PROGRAM or roles[11]!=TOKEN_PROGRAM or
                roles[12]!=PROGRAM or roles[13]!=str(event) or
                roles[14]!=PROGRAM or
                roles[9] not in keys[:tx.message.header.num_required_signatures]):
                raise ValueError("DBC signed original Anchor role mismatch")
            expected_mints=(fields["base_mint"],fields["quote_mint"]) if (
                 direction=="base_to_quote") else (fields["quote_mint"],fields["base_mint"])
            if (t.get("input_mint"),t.get("output_mint"))!=expected_mints:
                raise ValueError("DBC original signed mint direction inconsistent")
            wire_data=bytes(ix.data)
            if (len(wire_data)!=24 or wire_data[:8]!=DISC or
                int.from_bytes(wire_data[8:16],"little")!=amount or
                int.from_bytes(wire_data[16:24],"little")!=output):
                raise ValueError("DBC exact-in signed instruction/limit mismatch")
            raw_spl=t.get("post_spl_account_data_base64")
            if not isinstance(raw_spl,list) or len(raw_spl)!=2:
                raise ValueError("DBC original signed poststates incomplete")
            amounts=[]
            for encoded,mint in zip(raw_spl,expected_mints):
                spl=decode_token_account(base64.b64decode(encoded,validate=True))
                if spl["mint"]!=mint or spl["authority"]!=roles[9]:
                    raise ValueError("DBC post-SPL mint or owner differs from signed intent")
                amounts.append(spl["amount_base_units"])
            if amounts!=[0,output]:
                raise ValueError("DBC independent SPL debit/output differs from signed SDK/native")
            # Reconstruct both vault deltas independently from authenticated
            # original SPL bytes and simulated raw SPL vault poststates.
            vault_raw=t.get("post_vault_account_data_base64")
            if not isinstance(vault_raw,list) or len(vault_raw)!=2:
                raise ValueError("DBC two raw signed vault poststates required")
            before_vault=[];after_vault=[]
            for index,role in enumerate(("base_vault","quote_vault")):
                vault_address=fields[role]
                source_account=source_row["accounts"][vault_address]
                if source_account["owner"]!=TOKEN_PROGRAM:
                    raise ValueError("DBC original vault token program mismatch")
                saved=base64.b64decode(source_account["account_base64"],validate=True)
                if hashlib.sha256(saved).hexdigest()!=source_account["sha256"]:
                    raise ValueError("DBC original vault digest changed")
                current=base64.b64decode(vault_raw[index],validate=True)
                if len(saved)!=165 or len(current)!=165:
                    raise ValueError("DBC original/signed vault SPL lengths invalid")
                previous=decode_token_account(saved)
                latest=decode_token_account(current)
                mint=fields["base_mint" if index==0 else "quote_mint"]
                if (previous["mint"]!=mint or latest["mint"]!=mint or
                        previous["authority"]!=AUTHORITY or latest["authority"]!=AUTHORITY):
                    raise ValueError("DBC signed vault source mint or authority mismatch")
                before_vault.append(previous["amount_base_units"])
                after_vault.append(latest["amount_base_units"])
            input_index=0 if direction=="base_to_quote" else 1
            output_index=1-input_index
            if (after_vault[input_index]-before_vault[input_index]!=amount or
                    before_vault[output_index]-after_vault[output_index]!=output):
                raise ValueError("DBC independent vault input credit/output debit mismatch")
            logs=t.get("simulation_logs")
            if (not isinstance(logs,list) or
                not any("Program "+PROGRAM+" invoke" in x for x in logs) or
                not any("Program "+PROGRAM+" success" in x for x in logs)):
                raise ValueError("DBC genuine program success logs absent")
            hashes.append(hashlib.sha256(raw).hexdigest())
        if len(seen)!=4 or len(hashes)!=4:
            raise ValueError("DBC original four distinct signed trial coverage incomplete")
        result.append({"pool":address,"source_slot":source_row["source_slot"],
              "source_sha256":ref["source_pool_sha256"],
              "signed_transaction_hashes":hashes,
              "four_signed_original_sdk_native_spl_swaps_verified":True})
    return {"venue":"meteora_dbc",
       "status":"INDEPENDENT_DBC_ORIGINAL_SIGNED_NATIVE_SDK_SPL_PARITY",
       "independently_signed_verified_pools":len(result),
       "signed_trials_verified":4*len(result),"pools":result,
       "signed_parity_verified":True,
       "independent_signed_audit_verified":True,
       "registry_admission_approved":False,
       "actionable":False,"broadcast":False}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ("source","sdk","native","signed","output"):
        ap.add_argument("--"+name,required=True)
    ap.add_argument("--required",type=int,default=1);a=ap.parse_args()
    result=audit(*(json.loads(Path(getattr(a,n)).read_text())
                   for n in ("source","sdk","native","signed")),required=a.required)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
      "signed_trials_verified":result["signed_trials_verified"],
      "signed_verified_pools":result["independently_signed_verified_pools"]}))


if __name__=="__main__":main()
