"""End-to-end signed PumpSwap V2 Surfpool trial, following the Orca fork pattern.

Read-only upstream RPC, executable ELF provenance, isolated local account
hydration, fresh ephemeral signer, real sig-verified swap simulation and an
independent native/SDK receipt gate. Never calls sendTransaction.
"""
import argparse,base64,hashlib,json
from pathlib import Path
from solders.keypair import Keypair
from solders.hash import Hash
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.pumpswap_pool import PROGRAM,decode as decode_pool
from arb.pumpswap_fee_account import PROGRAM as FEE_PROGRAM
from arb.pumpswap_global_config import ADDRESS as GLOBAL,authenticated_buyback_wallets
from arb.pumpswap_account_resolver import resolve,ATA
from arb.pumpswap_local_simulation import local_rpc_only
from arb.pumpswap_trade_v2 import build_v2
from arb.pumpswap_signed_parity import run as verify_signed
from arb.pumpswap_sdk_candidate_audit import audit as sdk_audit
from arb.next_ten_pair_fixture_export import program_data_accounts
from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM
SYSTEM="11111111111111111111111111111111"
SAFE={"broadcast":False,"actionable":False,"registry_admission_approved":False}


def _raw(entry,owner):
    if (not isinstance(entry,dict) or entry.get("owner")!=owner
            or entry.get("executable") is not False):
        raise ValueError("untrusted PumpSwap source account owner")
    data=entry.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("missing PumpSwap source account bytes")
    raw=base64.b64decode(data[0],validate=True)
    if not raw or base64.b64encode(raw).decode()!=data[0]:
        raise ValueError("noncanonical PumpSwap source account bytes")
    return raw


def _set(rpc,address,owner,raw,lamports):
    if type(lamports) is not int or lamports<0:
        raise ValueError("untrusted source account lamports")
    call(rpc,"surfnet_setAccount",[address,{"lamports":lamports,
        "data":raw.hex(),"owner":owner,"executable":False}])


def _pda_ata(wallet,mint):
    return str(Pubkey.find_program_address(
        [bytes(Pubkey.from_string(wallet)),bytes(Pubkey.from_string(TOKEN_PROGRAM)),
         bytes(Pubkey.from_string(mint))],Pubkey.from_string(ATA))[0])


def _source_accounts(row):
    from arb.pumpswap_fee_account import authenticated_address
    fee_addr,_=authenticated_address()
    entries=row.get("authenticated_source_accounts")
    if not isinstance(entries,list) or len(entries)!=6:
        raise ValueError("six authenticated source accounts required")
    state=decode_pool(base64.b64decode(entries[0]["account_base64"],validate=True))
    addresses=[row["address"],state["base_vault"],state["quote_vault"],
               GLOBAL,fee_addr,state["base_mint"]]
    owners=[PROGRAM,TOKEN_PROGRAM,TOKEN_PROGRAM,PROGRAM,FEE_PROGRAM,TOKEN_PROGRAM]
    if any(r.get("address")!=a or r.get("owner")!=o
           for r,a,o in zip(entries,addresses,owners)):
        raise ValueError("source account identity or owner mismatch")
    result={}
    for row_entry,address,owner in zip(entries,addresses,owners):
        encoded=row_entry.get("account_base64")
        if not isinstance(encoded,str):
            raise ValueError("missing source account bytes")
        raw=base64.b64decode(encoded,validate=True)
        if not raw or base64.b64encode(raw).decode()!=encoded:
            raise ValueError("invalid source account bytes")
        lamports=row_entry.get("lamports")
        if type(lamports) is not int or lamports<0:
            raise ValueError("source capture lacks account lamports; recapture required")
        result[address]=(owner,raw,lamports)
    if row.get("mints")!=[state["base_mint"],state["quote_mint"]]:
        raise ValueError("source pool mints changed")
    return state,result


def _fresh_account(source_rpc,address,owner):
    result=call(source_rpc,"getAccountInfo",[address,{
        "encoding":"base64","commitment":"confirmed"}])
    entry=result.get("value")
    return owner,_raw(entry,owner),entry["lamports"]


def _hydrate(rpc,accounts):
    for address,(owner,data,lamports) in accounts.items():
        _set(rpc,address,owner,data,lamports)


def _fund_user(rpc,signer,state,input_mint,amount):
    owner=str(signer.pubkey())
    base=str(Keypair().pubkey())
    quote=str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,"data":"",
        "owner":SYSTEM,"executable":False}])
    for address,mint in ((base,state["base_mint"]),(quote,state["quote_mint"])):
        _set(rpc,address,TOKEN_PROGRAM,token_account_bytes(mint,owner,
             amount if mint==input_mint else 0),2039280)
    return base,quote


def execute(source_rpc,local_rpc,source,sdk,*,pool_count=1):
    local_rpc_only(local_rpc)
    sdk_audit(source,sdk)
    if type(pool_count) is not int or not 1<=pool_count<=7:
        raise ValueError("invalid bounded PumpSwap signed pool count")
    if len(sdk.get("pools",[]))!=pool_count:
        raise ValueError("SDK verified pool count mismatch")
    source_by_pool={r["address"]:r for r in source["pools"]}
    if len(source_by_pool)!=len(source["pools"]):
        raise ValueError("duplicate PumpSwap source identities")
    # Capture upgradeable loader accounts independently like Orca/DAMM v2.
    binaries=program_data_accounts(source_rpc,{PROGRAM,FEE_PROGRAM})
    hashes={}
    for program in (FEE_PROGRAM,PROGRAM):
        header=base64.b64decode(binaries[program]["data"][0],validate=True)
        programdata=str(Pubkey.from_bytes(header[4:36]))
        hashes[program]=hydrate(local_rpc,{"accounts":{
            program:binaries[program],programdata:binaries[programdata]}},
            program=program)
    verified_pools=[]
    for sdk_pool in sdk["pools"]:
        manifest={"venue":"pumpswap","trials":[]}
        address=sdk_pool["address"]
        source_row=source_by_pool[address]
        state,account_set=_source_accounts(source_row)
        if state["is_cashback_coin"]:
            raise ValueError("unsupported V2 cashback pool")
        # The base mint is part of the synchronized six-account snapshot.
        # Quote mint was omitted there: independently verify and hydrate it.
        account_set[state["quote_mint"]]=_fresh_account(
            source_rpc,state["quote_mint"],TOKEN_PROGRAM)
        _hydrate(local_rpc,account_set)
        config_raw=account_set[GLOBAL][1]
        wallet=authenticated_buyback_wallets(config_raw)[0]
        buyback_ata=_pda_ata(wallet,state["quote_mint"])
        recipient_ata=buyback_ata
        # The V2 buyback account is a quote ATA; account data is
        # zero-initialized only on an isolated Surfpool fork.
        _set(local_rpc,recipient_ata,TOKEN_PROGRAM,
             token_account_bytes(state["quote_mint"],wallet,0),2039280)
        from arb.pumpswap_global_config import decode as decode_global
        recipient=decode_global(config_raw)["protocol_fee_recipients"][0]
        for quote in sdk_pool["trials"]:
            mint=quote["input_mint"]
            size=quote["amount_in"]
            output=int(quote["official_sdk_output"])
            if (mint not in (state["base_mint"],state["quote_mint"])
                or type(size) is not int or size<=0 or output<=0
                or quote.get("status")!="OFFICIAL_SDK_CANDIDATE_EXACT"):
                raise ValueError("invalid SDK signed candidate")
            _hydrate(local_rpc,account_set)
            _set(local_rpc,recipient_ata,TOKEN_PROGRAM,
                 token_account_bytes(state["quote_mint"],wallet,0),2039280)
            signer=Keypair()
            user_base,user_quote=_fund_user(local_rpc,signer,state,mint,size)
            addresses=resolve({"verified":True,
                "canonical_pool_verified":True,"address":address,
                "base_mint":state["base_mint"],"quote_mint":state["quote_mint"],
                "base_vault":state["base_vault"],"quote_vault":state["quote_vault"],
                "coin_creator":state["coin_creator"],
                "global_config":{"protocol_fee_recipients":[recipient]}},
                str(signer.pubkey()),user_base,user_quote,recipient)
            addresses["buyback_fee_recipient"]=buyback_ata
            addresses["buyback_fee_recipient_authenticated"]=True
            direction=("sell" if mint==state["base_mint"]
                       else "buy_exact_quote_in")
            ix=build_v2(direction,addresses,size,output)
            blockhash=call(local_rpc,"getLatestBlockhash",[
                {"commitment":"confirmed"}])["value"]["blockhash"]
            tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],
                  Hash.from_string(blockhash))
            manifest["trials"].append({
                "pool":address,"input_mint":mint,
                "output_mint":state["quote_mint"] if direction=="sell" else state["base_mint"],
                "input_token_account":user_base if direction=="sell" else user_quote,
                "output_token_account":user_quote if direction=="sell" else user_base,
                "amount_in":size,"source_slot":sdk_pool["source_slot"],
                "source_digest":sdk_pool["source_digest"],
                "signed_transaction_base64":base64.b64encode(bytes(tx)).decode()})
        # Check this pool's four freshly signed transactions before moving to
        # another pool. Otherwise the early signed blockhash expires during
        # minutes of later pool hydration/provisioning (BlockhashNotFound).
        # No signature retries and no replaceRecentBlockhash shortcuts.
        pool_sdk={**sdk,"pools":[sdk_pool]}
        pool_proof=verify_signed(local_rpc,pool_sdk,manifest)
        if pool_proof.get("signed_parity_verified") is not True or len(pool_proof["pools"])!=1:
            raise ValueError("PumpSwap signed per-pool parity incomplete")
        verified_pools.extend(pool_proof["pools"])
    # The separate verifier checks real sig-verified SPL deltas; all verified
    # pool receipts are kept together for independent post-hoc cryptographic audit.
    proof={"venue":"pumpswap","status":"PUMPSWAP_SIGNED_SDK_NATIVE_EXACT",
           "pools":verified_pools,"signed_parity_verified":True,**SAFE}
    return {"venue":"pumpswap","status":"SIGNED_PUMPSWAP_ISOLATED_PARITY",
            "program_elf_sha256":hashes,"signed_proof":proof,**SAFE}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ("source-rpc","surfpool-rpc","source-report","sdk-report","output"):
        p.add_argument("--"+key,required=True)
    p.add_argument("--pool-count",type=int,default=1)
    args=p.parse_args()
    result=execute(args.source_rpc,args.surfpool_rpc,
       json.loads(Path(args.source_report).read_text()),
       json.loads(Path(args.sdk_report).read_text()),pool_count=args.pool_count)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"status":result["status"],"verified_pools":
        len(result["signed_proof"]["pools"])}))


if __name__=="__main__":
    main()
