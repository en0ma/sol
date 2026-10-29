"""Original Meteora DBC diagnostic signed swaps in isolated offline Surfpool.

This research runner is *not* signed acceptance until an independent native
full-fee quote parity and signed SPL/transaction auditor accept each trial.
Never calls mainnet write methods; only read-only source and offline localhost.
"""
import argparse,base64,hashlib,json
from pathlib import Path

from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction

from arb.rpc import call
from arb.meteora_dbc_seventh_venue_source import PROGRAM
from arb.meteora_dbc_seventh_state_capture import TOKEN_PROGRAM,CLOCK
from arb.meteora_dbc_swap import build_swap
from arb.pumpswap_local_simulation import local_rpc_only
from arb.next_ten_pair_fixture_export import program_data_accounts
from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate,_balances
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.orca_fork_clock import fork_clock
from arb.damm_cpmm_atomic_offline import _simulate
from arb.token_vaults import decode_token_account

SYSTEM="11111111111111111111111111111111"


def restore(local_rpc, address, evidence):
    if evidence.get("executable") is not False:
        raise ValueError("DBC source account executable restoration rejected")
    raw=base64.b64decode(evidence["account_base64"],validate=True)
    if hashlib.sha256(raw).hexdigest()!=evidence["sha256"]:
        raise ValueError("DBC source restoration hash changed")
    call(local_rpc,"surfnet_setAccount",[address,{
        "lamports":evidence["lamports"],"data":raw.hex(),
        "owner":evidence["owner"],"executable":False}])


def read_quote_mint(source_rpc, row):
    mint=row["pool_fields"]["quote_mint"]
    original_slot=row["source_slot"]
    reply=call(source_rpc,"getAccountInfo",[mint,{
        "encoding":"base64","commitment":"confirmed",
        "minContextSlot":original_slot}])
    acct=reply.get("value") if isinstance(reply,dict) else None
    if (not isinstance(acct,dict) or acct.get("owner")!=TOKEN_PROGRAM
            or acct.get("executable") is not False
            or not isinstance(acct.get("data"),list)
            or len(acct["data"])!=2 or acct["data"][1]!="base64"):
        raise ValueError("DBC unverified original SPL quote mint")
    raw=base64.b64decode(acct["data"][0],validate=True)
    if len(raw)!=82:raise ValueError("DBC quote mint original legacy SPL size invalid")
    return {"owner":TOKEN_PROGRAM,"executable":False,
        "account_base64":acct["data"][0],"lamports":acct["lamports"],
        "sha256":hashlib.sha256(raw).hexdigest(),
        "note":"quote mint read separately; not same-slot as pool"}


def provision(local_rpc, signer, input_mint, output_mint, amount):
    payer=str(signer.pubkey())
    source=str(Keypair().pubkey());dest=str(Keypair().pubkey())
    call(local_rpc,"surfnet_setAccount",[payer,{
        "lamports":5_000_000_000,"data":"",
        "owner":SYSTEM,"executable":False}])
    for address,mint,balance in (
            (source,input_mint,amount),(dest,output_mint,0)):
        call(local_rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,
            "data":token_account_bytes(mint,payer,balance).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    return source,dest


def diagnostic(source_rpc,local_rpc,source,sdk,curve,*,required=1):
    local_rpc_only(local_rpc)
    if source.get("status")=="SIX_DBC_ORIGINAL_SOURCE_POOLS_ONLY":
        if source.get("independent_audit",{}).get("authenticated_source_pools")!=6:
            raise ValueError("DBC six-source independently authenticated proof missing")
        source=source["source"]
    if (type(required) is not int or not 1<=required<=6 or
            source.get("status")!="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED" or
            sdk.get("status")!="DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY" or
            curve.get("status")!="INDEPENDENT_DBC_ORIGINAL_NATIVE_FEE_CURVE_SDK_PARITY"):
        raise ValueError("DBC signed diagnostic requires original unsigned source and Q64 curve evidence")
    pools=sorted(source["source_pools"],key=lambda r:r["clock_unix_timestamp"]);quoted={q["pool"]:q for q in sdk["pools"]}
    native={q["pool"]:q for q in curve["pools"]}
    if (curve.get("verified_pools")!=required or
            curve.get("verified_trials")!=required*4 or
            len(pools)!=required or len(quoted)!=required or len(native)!=required):
        raise ValueError("DBC signed diagnostic source/pool count mismatch")
    binaries=program_data_accounts(source_rpc,{PROGRAM})
    header=base64.b64decode(binaries[PROGRAM]["data"][0],validate=True)
    data_address=str(Pubkey.from_bytes(header[4:36]))
    elf_sha256=hydrate(local_rpc,{"accounts":{
       PROGRAM:binaries[PROGRAM],data_address:binaries[data_address]}},program=PROGRAM)
    reports=[]
    for row in pools:
        address=row["pool"];fields=row["pool_fields"]
        if (fields["pool_type"]!=0 or fields["is_migrated"]!=0 or
                fields["migration_progress"]!=0 or
                fields["base_token_program"]!=TOKEN_PROGRAM or
                fields["quote_token_program"]!=TOKEN_PROGRAM):
            raise ValueError("DBC diagnostics restrict original standard SPL source")
        if address not in quoted or address not in native:
            raise ValueError("DBC missing original SDK/native curve evidence")
        if native[address]["source_config_sha256"]!=row["accounts"][fields["config"]]["sha256"]:
            raise ValueError("DBC native curve input not same original config")
        target=row["clock_unix_timestamp"]
        observed=fork_clock(local_rpc)["fork_unix_timestamp"]
        # Historical authentic snapshots may predate the wall clock.
        # Move only the isolated paused Surfpool clock, never the mainnet RPC.
        if observed!=target:
            call(local_rpc,"surfnet_timeTravel",[{"absoluteTimestamp":target*1000}])
        if fork_clock(local_rpc)["fork_unix_timestamp"]!=target:
            raise ValueError("DBC fork Clock mismatch")
        quote_mint=read_quote_mint(source_rpc,row)
        hydrate_accounts=dict(row["accounts"])
        hydrate_accounts[fields["quote_mint"]]=quote_mint
        ordered=[(addr,acct) for addr,acct in hydrate_accounts.items() if addr!=CLOCK]
        receipts=[]
        for trial in quoted[address]["trials"]:
            # Every trial starts at identical original source bytes.
            for addr,acct in ordered:restore(local_rpc,addr,acct)
            direction=trial["direction"]
            base=direction=="base_to_quote"
            mint_in=fields["base_mint"] if base else fields["quote_mint"]
            mint_out=fields["quote_mint"] if base else fields["base_mint"]
            amount=int(trial["amount_in"])
            expected=int(trial["sdk_output"])
            if not 0<amount<1<<64 or not 0<expected<1<<64:
                raise ValueError("DBC SDK quote nonpositive/overflow")
            signer=Keypair()
            user_in,user_out=provision(local_rpc,signer,mint_in,mint_out,amount)
            ix,_=build_swap(address,fields,str(signer.pubkey()),
                  user_in,user_out,amount,expected,
                  swap_base_for_quote=base)
            blockhash=call(local_rpc,"getLatestBlockhash",[
                {"commitment":"confirmed"}])["value"]["blockhash"]
            signed=Transaction.new_signed_with_payer([
                ix],signer.pubkey(),[signer],Hash.from_string(blockhash))
            simulated,_=_simulate(local_rpc,signed,[user_in,user_out,
                fields["base_vault"],fields["quote_vault"]])
            if simulated.get("err") is not None:
                raise ValueError("DBC isolated original signed swap rejected: "+
                                 str(simulated["err"])[:180])
            accounts=simulated.get("accounts")
            if not isinstance(accounts,list) or len(accounts)!=4 or any(
                    not isinstance(a,dict) or a.get("owner")!=TOKEN_PROGRAM or
                    not isinstance(a.get("data"),list) or len(a["data"])!=2 or
                    a["data"][1]!="base64" for a in accounts):
                raise ValueError("DBC signed user/vault poststates missing")
            post=_balances({"accounts":accounts[:2]},(mint_in,mint_out),str(signer.pubkey()))
            if post!=[0,expected]:
                raise ValueError("DBC original SPL output differs from official SDK")
            logs=simulated.get("logs")
            if (not isinstance(logs,list) or
                not any("Program "+PROGRAM+" invoke" in line for line in logs) or
                not any("Program "+PROGRAM+" success" in line for line in logs)):
                raise ValueError("DBC original signed success logs absent")
            vault_before=[];vault_after=[]
            for index,key in enumerate(("base_vault","quote_vault")):
                original=decode_token_account(base64.b64decode(
                    row["accounts"][fields[key]]["account_base64"],validate=True))
                current=decode_token_account(base64.b64decode(
                    accounts[index+2]["data"][0],validate=True))
                expected_mint=fields["base_mint" if index==0 else "quote_mint"]
                if (original["mint"]!=expected_mint or current["mint"]!=expected_mint or
                        original["authority"]!=current["authority"]):
                    raise ValueError("DBC original vault versus signed vault identity mismatch")
                vault_before.append(original["amount_base_units"])
                vault_after.append(current["amount_base_units"])
            input_idx=0 if base else 1
            output_idx=1-input_idx
            if (vault_after[input_idx]-vault_before[input_idx]!=amount or
                    vault_before[output_idx]-vault_after[output_idx]!=expected):
                raise ValueError("DBC signed original vault flow differs from native/SDK")
            receipts.append({"direction":direction,"amount_in":amount,
                 "pool":address,"source_slot":row["source_slot"],
                 "source_pool_sha256":row["accounts"][address]["sha256"],
                 "input_mint":mint_in,"output_mint":mint_out,
                 "input_token_account":user_in,"output_token_account":user_out,
                 "signed_signature":str(signed.signatures[0]),
                 "post_spl_account_data_base64":[a["data"][0] for a in accounts[:2]],
                 "post_vault_account_data_base64":[a["data"][0] for a in accounts[2:]],
                 "simulation_logs":logs,
                 "sdk_expected_output":expected,
                 "raw_signed_transaction_base64":base64.b64encode(bytes(signed)).decode(),
                 "raw_signed_transaction_sha256":hashlib.sha256(bytes(signed)).hexdigest(),
                 "observed_output":post[1],
                 "note":"diagnostic only: full independent fee and signed SPL audit pending"})
        reports.append({"pool":address,"source_slot":row["source_slot"],
                        "trials":receipts})
    return {"status":"DBC_SIGNED_OFFLINE_DIAGNOSTIC_NOT_ACCEPTED",
       "source_program_elf_sha256":elf_sha256,
       "pools":reports,"diagnostic_signed_trials":4*len(reports),
       "independent_signed_audit_accepted":False,
       "native_full_fee_sdk_parity":False,
       "registry_admission_approved":False,"actionable":False,"broadcast":False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-rpc",required=True);p.add_argument("--surfpool-rpc",required=True)
    p.add_argument("--source",required=True);p.add_argument("--sdk",required=True)
    p.add_argument("--curve",required=True);p.add_argument("--required",type=int,default=1)
    p.add_argument("--output",required=True);a=p.parse_args()
    result=diagnostic(a.source_rpc,a.surfpool_rpc,
       json.loads(Path(a.source).read_text()),
       json.loads(Path(a.sdk).read_text()),
       json.loads(Path(a.curve).read_text()),required=a.required)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],
                      "diagnostic_signed_trials":result["diagnostic_signed_trials"],
                      "independent_signed_audit_accepted":False}))


if __name__=="__main__":main()
