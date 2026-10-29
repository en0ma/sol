"""Fifth venue: four genuine signed Meteora DLMM swaps on isolated Surfpool.

Mirrors Orca/DAMM v2: authenticate existing same-slot source evidence, load
the REAL upgradeable ELF and bin-array state into offline Surfpool, provision
ephemeral users, sign legacy DLMM exact-in instructions and require observed
SPL outputs equal independent Python integer-bin and official JS SDK quotes.
No sendTransaction; source RPC is only read.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.keypair import Keypair
from solders.hash import Hash
from solders.transaction import Transaction
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.meteora_dlmm import PROGRAM,decode
from arb.meteora_dlmm_swap import build_swap
from arb.meteora_dlmm_native_candidate_audit import calculate as native_audit
from arb.meteora_dlmm_fifth_venue_source import CLOCK,SYSVAR
from arb.pumpswap_local_simulation import local_rpc_only
from arb.next_ten_pair_fixture_export import program_data_accounts
from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate,_balances
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM
from arb.damm_cpmm_atomic_offline import _simulate

SYSTEM="11111111111111111111111111111111"
SAFE={"actionable":False,"broadcast":False,
      "live_execution_approved":False,"registry_admission_approved":False}


def _restore(rpc,account):
    if account.get("present") is False:
        return
    owner=account.get("owner")
    encoded=account.get("account_base64")
    lamports=account.get("lamports")
    if (not isinstance(owner,str) or not isinstance(encoded,str)
            or type(lamports) is not int or lamports<0):
        raise ValueError("DLMM source hydration account provenance incomplete")
    raw=base64.b64decode(encoded,validate=True)
    if not raw or base64.b64encode(raw).decode()!=encoded:
        raise ValueError("DLMM malformed source hydration account bytes")
    call(rpc,"surfnet_setAccount",[account["address"],{
        "lamports":lamports,"data":raw.hex(),"owner":owner,"executable":False}])


def _provision(rpc,signer,mint_in,mint_out,amount):
    payer=str(signer.pubkey())
    user_in=str(Keypair().pubkey())
    user_out=str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[payer,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    for address,mint,balance in (
            (user_in,mint_in,amount),(user_out,mint_out,0)):
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,"data":token_account_bytes(mint,payer,balance).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    return user_in,user_out


def execute(source_rpc,local_rpc,source,sdk,*,pool_count=1):
    local_rpc_only(local_rpc)
    if type(pool_count) is not int or not 1<=pool_count<=3:
        raise ValueError("DLMM bounded signed pool count invalid")
    independent=native_audit(source,sdk)
    if independent["verified_pools"]!=pool_count:
        raise ValueError("signed DLMM pool count differs from independent SDK/native parity")
    index={r["address"]:r for r in source["pools"]}
    native_index={r["pool"]:r for r in independent["pools"]}
    binaries=program_data_accounts(source_rpc,{PROGRAM})
    header=base64.b64decode(binaries[PROGRAM]["data"][0],validate=True)
    data_address=str(Pubkey.from_bytes(header[4:36]))
    elf_hash=hydrate(local_rpc,{"accounts":{
        PROGRAM:binaries[PROGRAM],data_address:binaries[data_address]}},program=PROGRAM)
    reports=[]
    for quote_pool in sdk["pools"]:
        address=quote_pool["pool"]
        row=index[address]
        native=native_index[address]
        if row["source_sha256"]!=native["source_sha256"]:
            raise ValueError("DLMM source digest changed after native audit")
        account_set=[r for r in row["source_accounts"] if r["address"]!=CLOCK]
        # The core Clock sysvar belongs to the isolated emulator; all DLMM
        # program-owned state is restored from authenticated source accounts.
        for account in account_set:
            _restore(local_rpc,account)
        base_state=decode(base64.b64decode(row["source_accounts"][0][
            "account_base64"],validate=True))
        available={a["pda"] for a in row["bin_arrays"] if a["authenticated"]}
        by_quote={(q["input_mint"],q["amount_in"]):q for q in quote_pool["trials"]}
        proofs=[]
        for candidate in native["trials"]:
            direction=candidate["direction"]
            amount=candidate["amount_in"]
            mint_in=candidate["mint_in"]
            mint_out=candidate["mint_out"]
            official=by_quote[(mint_in,amount)]
            path=official["bin_array_path"]
            if (not isinstance(path,list) or not path or len(path)>3 or
                    len(set(path))!=len(path) or any(p not in available for p in path)):
                raise ValueError("DLMM SDK bin-array path not in authenticated source neighborhood")
            expected=candidate["native_integer_output"]
            if expected!=candidate["official_sdk_output"] or expected<=0:
                raise ValueError("DLMM official/native candidate output mismatch")
            # Each genuine swap runs from identical pool reserves and bin
            # liquidity; do not accumulate earlier trial changes.
            for account in account_set:
                _restore(local_rpc,account)
            signer=Keypair()
            user_input,user_output=_provision(
                local_rpc,signer,mint_in,mint_out,amount)
            state={**base_state,"input_mint":mint_in,
                   "output_mint":mint_out,
                   "active_bin_array_index":row["bin_arrays"][1]["index"]}
            ix=build_swap(address,state,str(signer.pubkey()),
                user_input,user_output,base_state["oracle"],path,
                amount,expected,input_is_x=direction=="x_to_y")
            blockhash=call(local_rpc,"getLatestBlockhash",[
                {"commitment":"confirmed"}])["value"]["blockhash"]
            tx=Transaction.new_signed_with_payer(
                [ix],signer.pubkey(),[signer],Hash.from_string(blockhash))
            simulated,_=_simulate(local_rpc,tx,[user_input,user_output])
            if simulated.get("err") is not None:
                raise ValueError("signed DLMM real program rejected swap: "+
                                 str(simulated["err"])[:240])
            received=_balances(simulated,(mint_in,mint_out),str(signer.pubkey()))
            if received!=[0,expected]:
                raise ValueError("signed DLMM SPL debits/credits differ from SDK/native")
            logs=simulated.get("logs")
            if (not isinstance(logs,list) or
                    not any("Program "+PROGRAM+" invoke" in line for line in logs) or
                    not any("Program "+PROGRAM+" success" in line for line in logs)):
                raise ValueError("DLMM signed execution program success logs missing")
            accounts=simulated.get("accounts")
            proofs.append({
                "pool":address,"direction":direction,
                "input_mint":mint_in,"output_mint":mint_out,"amount_in":amount,
                "signed_output":received[1],"official_sdk_output":expected,
                "native_integer_output":expected,
                "source_slot":row["source_slot"],
                "source_sha256":row["source_sha256"],
                "input_token_account":user_input,"output_token_account":user_output,
                "signed_transaction_base64":base64.b64encode(bytes(tx)).decode(),
                "signed_sha256":hashlib.sha256(bytes(tx)).hexdigest(),
                "signed_signature":str(tx.signatures[0]),
                "post_spl_account_data_base64":[a["data"][0] for a in accounts],
                "simulation_logs":logs,
                "status":"SIGNED_DLMM_SDK_NATIVE_SPL_EXACT"})
        if len(proofs)!=4 or len({p["signed_signature"] for p in proofs})!=4:
            raise ValueError("four distinct signed DLMM swap receipts required")
        reports.append({"pool":address,"source_slot":row["source_slot"],
                        "source_sha256":row["source_sha256"],"trials":proofs,
                        "verified":True})
    return {"venue":"meteora_dlmm","status":"DLMM_REAL_SIGNED_SDK_NATIVE_SPL_PARITY",
            "verified_pools":len(reports),"pools":reports,
            "dlmm_program_elf_sha256":elf_hash,
            "signed_parity_verified":True,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for field in ("source-rpc","surfpool-rpc","source","sdk","output"):
        p.add_argument("--"+field,required=True)
    p.add_argument("--pool-count",type=int,default=1)
    a=p.parse_args()
    result=execute(a.source_rpc,a.surfpool_rpc,
        json.loads(Path(a.source).read_text()),json.loads(Path(a.sdk).read_text()),
        pool_count=a.pool_count)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":len(result["pools"])}))


if __name__=="__main__":
    main()
