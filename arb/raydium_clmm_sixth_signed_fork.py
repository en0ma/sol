"""Sixth venue: real signed Raydium CLMM SwapV2 four-trial isolated fork.

One authenticated source snapshot (pool/vaults/config/observation/mints and
nine tick arrays) is used for independent native Q64 and official Raydium
SDK comparison. Genuine Ephemeral Ed25519-signed SwapV2 instructions execute
in local Surfpool with the *real* upgradeable CLMM ELF. Read-only mainnet
never receives a signed transaction. This runner cannot authorize broadcast.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.keypair import Keypair
from solders.hash import Hash
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.raydium_clmm import PROGRAM,decode
from arb.raydium_clmm_swap import build
from arb.raydium_clmm_native_single_tick import evaluate
from arb.pumpswap_local_simulation import local_rpc_only
from arb.next_ten_pair_fixture_export import program_data_accounts
from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate,_balances
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM
from arb.damm_cpmm_atomic_offline import _simulate

SYSTEM="11111111111111111111111111111111"
SAFE={"actionable":False,"broadcast":False,"registry_admission_approved":False,
      "live_execution_approved":False}


def _restore(rpc,account):
    if account.get("present") is False:return
    owner=account.get("owner")
    encoded=account.get("account_base64")
    lamports=account.get("lamports")
    if (not isinstance(owner,str) or not isinstance(encoded,str)
            or type(lamports) is not int or lamports<0):
        raise ValueError("CLMM authenticated hydration data incomplete")
    raw=base64.b64decode(encoded,validate=True)
    if not raw or base64.b64encode(raw).decode()!=encoded:
        raise ValueError("CLMM hydrated source bytes noncanonical")
    call(rpc,"surfnet_setAccount",[account["address"],{
        "lamports":lamports,"owner":owner,"data":raw.hex(),"executable":False}])


def _provision(rpc,signer,mint_input,mint_output,amount):
    owner=str(signer.pubkey())
    source=str(Keypair().pubkey())
    destination=str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    for account,mint,balance in (
            (source,mint_input,amount),(destination,mint_output,0)):
        call(rpc,"surfnet_setAccount",[account,{
            "lamports":2039280,
            "data":token_account_bytes(mint,owner,balance).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    return source,destination


def execute(source_rpc,local_rpc,tick_source,native,sdk):
    local_rpc_only(local_rpc)
    if (not isinstance(sdk,dict) or sdk.get("venue")!="raydium_clmm"
            or sdk.get("status")!="RAYDIUM_CLMM_NATIVE_SDK_SINGLE_TICK_EXACT"
            or sdk.get("official_sdk_native_parity_verified") is not True
            or sdk.get("signed_parity_verified") is not False
            or any(sdk.get(k) is not False for k in
                   ("broadcast","actionable","registry_admission_approved"))):
        raise ValueError("CLMM authenticated official SDK price-parity report required")
    local=evaluate(tick_source)
    original={row["pool"]:row for row in tick_source["pools"]}
    candidates={row["pool"]:row for row in local["pools"]}
    if (not isinstance(sdk.get("pools"),list) or
            len(original)!=len(sdk["pools"]) or not 1<=len(original)<=3):
        raise ValueError("CLMM signed pool count or source identity invalid")
    binaries=program_data_accounts(source_rpc,{PROGRAM})
    header=base64.b64decode(binaries[PROGRAM]["data"][0],validate=True)
    programdata=str(Pubkey.from_bytes(header[4:36]))
    elf_hash=hydrate(local_rpc,{"accounts":{
        PROGRAM:binaries[PROGRAM],programdata:binaries[programdata]}},program=PROGRAM)
    reports=[]
    for reference in sdk["pools"]:
        address=reference["pool"]
        captured=original.get(address)
        candidate=candidates.get(address)
        if (not captured or not candidate or
                reference.get("tick_snapshot_sha256")!=captured["tick_snapshot_sha256"]
                or candidate["snapshot_sha256"]!=captured["tick_snapshot_sha256"]):
            raise ValueError("CLMM signed pool source/SDK hash does not match")
        tick=captured["tick_capture"]
        accounts=tick.get("synchronized_non_tick_accounts")
        if not isinstance(accounts,list) or len(accounts)!=7:
            raise ValueError("CLMM complete same-slot pool/vault/config/obs/mints required")
        tick_accounts=[x for x in tick["tick_arrays"] if x["present"]]
        originals=[*accounts,*tick_accounts]
        state=decode(base64.b64decode(accounts[0]["account_base64"],validate=True))
        verified_arrays={r["address"] for r in tick_accounts}
        native_quotes={(q["zero_for_one"],q["amount_in"]):q
                       for q in candidate["quotes"]}
        sdk_quotes=reference.get("trials")
        if (not isinstance(sdk_quotes,list) or len(sdk_quotes)!=4
                or len(native_quotes)!=4):
            raise ValueError("CLMM exactly four verified native/SDK trials required")
        proofs=[]
        for quote in sdk_quotes:
            forward=quote["zero_for_one"]
            size=quote["amount_in"]
            if type(forward) is not bool or type(size) is not int or size<=0:
                raise ValueError("CLMM signed trial input identity invalid")
            native_trial=native_quotes.get((forward,size))
            if (not native_trial or quote.get("status")!="OFFICIAL_SDK_NATIVE_SINGLE_TICK_EXACT"
                    or quote.get("all_trade") is not True
                    or str(native_trial["output"])!=quote.get("official_sdk_output")
                    or str(native_trial["fee"])!=quote.get("official_fee")):
                raise ValueError("CLMM official price/fee differs from authenticated native integer")
            path=quote.get("remaining_tick_arrays")
            if (not isinstance(path,list) or not 1<=len(path)<=5
                    or len(set(path))!=len(path)
                    or any(account not in verified_arrays for account in path)):
                raise ValueError("CLMM official SDK tick path not in authenticated snapshot")
            # Each signed simulation is isolated from its siblings.
            for account in originals:_restore(local_rpc,account)
            signer=Keypair()
            mint_in=state["token_mint_0" if forward else "token_mint_1"]
            mint_out=state["token_mint_1" if forward else "token_mint_0"]
            if quote.get("input_mint")!=mint_in or quote.get("output_mint")!=mint_out:
                raise ValueError("CLMM signed SDK mint direction mismatch")
            user_in,user_out=_provision(local_rpc,signer,mint_in,mint_out,size)
            output=native_trial["output"]
            ix=build(address,state,str(signer.pubkey()),user_in,user_out,
                size,output,path,input_is_token_0=forward)
            blockhash=call(local_rpc,"getLatestBlockhash",[
                {"commitment":"confirmed"}])["value"]["blockhash"]
            tx=Transaction.new_signed_with_payer(
                [ix],signer.pubkey(),[signer],Hash.from_string(blockhash))
            simulated,_=_simulate(local_rpc,tx,[user_in,user_out])
            if simulated.get("err") is not None:
                raise ValueError("CLMM genuine signed SwapV2 rejected: "+
                                 str(simulated["err"])[:200])
            balances=_balances(simulated,[mint_in,mint_out],str(signer.pubkey()))
            if balances!=[0,output]:
                raise ValueError("CLMM genuine signed SPL amount differs from native/SDK "+
                                 str(balances)+" expected="+str(output))
            logs=simulated.get("logs")
            if (not isinstance(logs,list) or
                    not any("Program "+PROGRAM+" invoke" in line for line in logs)
                    or not any("Program "+PROGRAM+" success" in line for line in logs)):
                raise ValueError("CLMM signed on-chain program success not observed")
            proofs.append({"pool":address,"zero_for_one":forward,"amount_in":size,
                "input_mint":mint_in,"output_mint":mint_out,
                "input_token_account":user_in,"output_token_account":user_out,
                "source_slot":tick["tick_array_source_slot"],
                "tick_snapshot_sha256":captured["tick_snapshot_sha256"],
                "official_sdk_output":output,"native_integer_output":output,
                "signed_spl_output":balances[1],
                "signed_transaction_base64":base64.b64encode(bytes(tx)).decode(),
                "signed_sha256":hashlib.sha256(bytes(tx)).hexdigest(),
                "signed_signature":str(tx.signatures[0]),
                "simulation_logs":logs,
                "post_spl_account_data_base64":[a["data"][0]
                    for a in simulated["accounts"]],
                "status":"SIGNED_RAYDIUM_CLMM_NATIVE_SDK_SPL_EXACT"})
        if (len(proofs)!=4 or len({r["signed_signature"] for r in proofs})!=4
                or len({(r["zero_for_one"],r["amount_in"]) for r in proofs})!=4):
            raise ValueError("CLMM four distinct signed trials required")
        reports.append({"pool":address,"verified":True,
            "source_slot":tick["tick_array_source_slot"],
            "tick_snapshot_sha256":captured["tick_snapshot_sha256"],
            "trials":proofs})
    return {"venue":"raydium_clmm",
        "status":"SIGNED_RAYDIUM_CLMM_NATIVE_SDK_SPL_PARITY",
        "signed_parity_verified":True,"verified_pools":len(reports),
        "program_elf_sha256":elf_hash,"pools":reports,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("source-rpc","surfpool-rpc","tick-source","native","sdk","output"):
        p.add_argument("--"+name,required=True)
    a=p.parse_args()
    proof=execute(a.source_rpc,a.surfpool_rpc,
        json.loads(Path(a.tick_source).read_text()),
        json.loads(Path(a.native).read_text()),
        json.loads(Path(a.sdk).read_text()))
    Path(a.output).write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps({"status":proof["status"],"signed_pools":proof["verified_pools"]}))
if __name__=="__main__":main()
