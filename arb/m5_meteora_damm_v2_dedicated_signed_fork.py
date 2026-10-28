"""Dedicated Meteora DAMM v2 fork validation (no unrelated route dependency).

Authenticate registered real pool+vaults+program ELF on the isolated fork;
run signed swap2 in both directions; compare SPL output to Meteora official SDK.
On failure, emit an explicit diagnostic receipt, NEVER a validated status.
"""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
from solders.keypair import Keypair
from solders.hash import Hash
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.next_ten_pair_fixture_export import venue_accounts,program_data_accounts
from arb.next_ten_signed_atomic_offline import local_rpc_only
from arb.damm_cpmm_atomic_offline import _simulate
from arb.meteora_damm_v2 import PROGRAM,decode,verify as verify_pool
from arb.meteora_damm_v2_swap import build_swap2
from arb.meteora_damm_v2_source_fee_decoder import decode_fee_state
from arb.orca_fork_clock import fork_clock,stable_orca_fork_clock
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
LOADER="BPFLoaderUpgradeab1e11111111111111111111111"
SYSTEM="11111111111111111111111111111111"

def capture(rpc,address):
    local_rpc_only(rpc)
    if not isinstance(address,str) or not address:
        raise ValueError("source Meteora pool address missing")
    proof=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])
    entry=proof.get("value")
    if not isinstance(entry,dict) or entry.get("owner")!=PROGRAM or entry.get("executable") is not False:
        raise ValueError("unverified source Meteora pool owner: "+
                         ("missing_account" if entry is None else
                          "observed_owner="+str(entry.get("owner"))+
                          " executable="+str(entry.get("executable"))))
    raw=base64.b64decode(entry["data"][0],validate=True)
    state=decode(raw)
    if state["pool_status"]!=0 or state["token_a_flag"] or state["token_b_flag"]:
        raise ValueError("source Meteora pool disabled/nonclassic SPL")
    verified=verify_pool(rpc,address,state)
    addresses=[address,state["token_a_vault"],state["token_b_vault"],
               state["token_a_mint"],state["token_b_mint"]]
    reply=call(rpc,"getMultipleAccounts",[addresses,
                 {"encoding":"base64","commitment":"confirmed"}])
    values=reply.get("value")
    slot=reply.get("context",{}).get("slot")
    if type(slot)is not int or not isinstance(values,list) or any(not isinstance(v,dict) for v in values):
        raise ValueError("Meteora source accounts not captured at one RPC slot")
    accounts=dict(zip(addresses,values))
    if accounts[address]["owner"]!=PROGRAM or decode(base64.b64decode(accounts[address]["data"][0],validate=True))!=state:
        raise ValueError("Meteora source pool mutated during capture")
    accounts.update(program_data_accounts(rpc,{PROGRAM}))
    return {"pool":address,"state":state,"slot":slot,"accounts":accounts,
            "source_pool_data_base64":accounts[address]["data"][0],
            "verified_vault_reserves":verified["vault_base_units"],
            "source_fee_state":decode_fee_state(raw)}

def export_source(rpc,registry,output,*,pool_count=1):
    """Capture six DISTINCT authenticated real DAMM pools, never one pool repeated."""
    if type(pool_count)is not int or not 1<=pool_count<=12:
        raise ValueError("DAMM unique pool count invalid")
    candidates=list(dict.fromkeys(row["address"] for row in registry["pools"]
                    if row.get("venue")=="meteora_damm_v2"))
    attempts=[]
    selected=[]
    for address in candidates:
        try:
            captured=capture(rpc,address)
            selected.append(captured)
            if len(selected)==pool_count:
                break
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            attempts.append({"pool":address,"reason":str(exc)[:250]})
    Path(output).write_text(json.dumps(
        {"selected_pools":selected,"source_attempts":attempts,
         "required_distinct_pools":pool_count,**SAFE},
        sort_keys=True,indent=2)+"\n")
    return len(selected)==pool_count

def hydrate(rpc,captured,*,program=PROGRAM):
    accounts=captured["accounts"]
    executable=accounts[program]
    header=base64.b64decode(executable["data"][0],validate=True)
    if executable["owner"]!=LOADER or executable.get("executable") is not True or header[:4]!=bytes([2,0,0,0]):
        raise ValueError("invalid Meteora executable provenance")
    address=str(Pubkey.from_bytes(header[4:36]))
    pd=accounts[address]
    raw=base64.b64decode(pd["data"][0],validate=True)
    if pd["owner"]!=LOADER or raw[:4]!=bytes([3,0,0,0]) or raw[45:49]!=bytes([127,69,76,70]):
        raise ValueError("invalid Meteora program ELF")
    elf=raw[45:]
    for addr,entry in accounts.items():
        if addr in (program,address):continue
        if entry.get("executable") is not False:
            raise ValueError("non-program executable source account")
        call(rpc,"surfnet_setAccount",[addr,{
             "lamports":entry["lamports"],
             "data":base64.b64decode(entry["data"][0],validate=True).hex(),
             "owner":entry["owner"],"executable":False}])
    for offset in range(0,len(elf),16384):
        call(rpc,"surfnet_writeProgram",[program,elf[offset:offset+16384].hex(),offset])
    return hashlib.sha256(elf).hexdigest()

def _balances(positive,mints,authority):
    result=positive.get("accounts")
    if not isinstance(result,list) or len(result)!=2:
        raise ValueError("signed Meteora SPL post accounts missing")
    amounts=[]
    for entry,mint in zip(result,mints):
        if not isinstance(entry,dict) or entry.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("signed Meteora SPL account owner invalid")
        data=entry.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("signed Meteora SPL account bytes missing")
        token=decode_token_account(base64.b64decode(data[0],validate=True))
        if token["mint"]!=mint or token["authority"]!=authority:
            raise ValueError("signed Meteora SPL output mint/authority invalid")
        amounts.append(token["amount_base_units"])
    return amounts

def signed_trial(rpc,captured,amount,input_is_a,binary):
    if type(amount)is not int or not 0<amount<2**64 or type(input_is_a)is not bool:
        raise ValueError("Meteora signed exact-input arguments invalid")
    state=captured["state"]
    mint_in=state["token_a_mint" if input_is_a else "token_b_mint"]
    mint_out=state["token_b_mint" if input_is_a else "token_a_mint"]
    signer=Keypair()
    owner=str(signer.pubkey())
    src,dst=str(Keypair().pubkey()),str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
        "data":"","owner":SYSTEM,"executable":False}])
    for key,mint,balance in ((src,mint_in,amount),(dst,mint_out,0)):
        call(rpc,"surfnet_setAccount",[key,{"lamports":2039280,
            "data":token_account_bytes(mint,owner,balance).hex(),
            "owner":TOKEN_PROGRAM,"executable":False}])
    call(rpc,"surfnet_pauseClock",[])
    try:
        before=fork_clock(rpc)
        ix=build_swap2(captured["pool"],state,owner,src,dst,amount,1,
                       input_is_a=input_is_a)
        latest=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer(
            [ix],signer.pubkey(),[signer],Hash.from_string(latest))
        positive,_=_simulate(rpc,tx,[src,dst])
        if positive.get("err") is not None:
            raise ValueError("Meteora signed swap2 rejected: "+str(positive["err"])[:230])
        balances=_balances(positive,(mint_in,mint_out),owner)
        if balances[0]!=0 or balances[1]<=0:
            raise ValueError("Meteora signed exact input did not debit/credit user")
        after=fork_clock(rpc)
        clock=stable_orca_fork_clock(before,after)
        if (not clock["fork_clock_stable_for_quote"] or
                before["fork_clock_slot"]!=after["fork_clock_slot"]):
            raise ValueError("Meteora signed Clock not pinned")
        request={"pool_data_base64":captured["source_pool_data_base64"],
                 "amount_in":amount,"input_is_a":input_is_a,
                 "fork_unix_timestamp":before["fork_unix_timestamp"],
                 "fork_clock_slot":before["fork_clock_slot"]}
        official=subprocess.run([binary],input=json.dumps(request),
            text=True,capture_output=True,timeout=90)
        if official.returncode:
            raise ValueError("official Meteora SDK refused quote: "+official.stderr[-250:])
        result=json.loads(official.stdout)
        quoted=result.get("amount_out")
        if type(quoted)is not int:
            raise ValueError("official Meteora native quote missing")
        signed=balances[1]
        return {"status":("METEORA_DAMM_V2_OFFICIAL_SIGNED_EXACT"
                          if quoted==signed else "METEORA_DAMM_V2_OFFICIAL_SIGNED_MISMATCH"),
                "pool":captured["pool"],"direction":"a_to_b" if input_is_a else "b_to_a",
                "input":amount,"official_output":quoted,"signed_output":signed,
                "native_minus_signed":quoted-signed,"source_slot":captured["slot"],
                "fork_clock":clock,"signed_sha256":hashlib.sha256(bytes(tx)).hexdigest(),
                "signed_signature":str(tx.signatures[0]),**SAFE}
    finally:
        call(rpc,"surfnet_resumeClock",[])

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--registry")
    p.add_argument("--capture-source",action="store_true")
    p.add_argument("--source-file")
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amounts",default="10000,100000")
    p.add_argument("--pool-count",type=int,default=1)
    p.add_argument("--a-to-b-amounts",default="10000000,100000000")
    a=p.parse_args()
    rpc="http://127.0.0.1:8899"
    if a.capture_source:
        if not a.registry or not a.source_file:
            raise SystemExit("Meteora upstream source capture requires registry and source-file")
        registry=json.loads(Path(a.registry).read_text())
        result=export_source(rpc,registry,a.source_file,pool_count=a.pool_count)
        print(json.dumps({"status":"METEORA_UPSTREAM_SOURCE_CAPTURED" if result
                          else "METEORA_UPSTREAM_SOURCE_MISSING",**SAFE}))
        if not result:
            raise SystemExit("No source authenticated DAMM pool")
        return
    if not a.source_file:
        raise SystemExit("Meteora offline trials require captured upstream source fixture")
    source=json.loads(Path(a.source_file).read_text())
    selected=source.get("selected_pools")
    attempts=source.get("source_attempts",[])
    if (not isinstance(selected,list) or len(selected)!=a.pool_count or
            len({p.get("pool") for p in selected})!=a.pool_count):
        raise SystemExit("six distinct source-authenticated DAMM pools required")
    reports=[]
    for pool in selected:
        trials=[]
        try:
            hydrate(rpc,pool)
            for a_to_b in (True,False):
                sizes=a.a_to_b_amounts if a_to_b else a.amounts
                for amount in (int(x) for x in sizes.split(",")):
                    try:
                        receipt=signed_trial(rpc,pool,amount,a_to_b,a.binary)
                    except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                        receipt={"status":"METEORA_SIGNED_FORK_BLOCKED",
                                 "direction":"a_to_b" if a_to_b else "b_to_a",
                                 "amount":amount,"reason":str(exc)[:300],**SAFE}
                    trials.append(receipt)
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            trials.append({"status":"METEORA_POOL_HYDRATION_BLOCKED",
                           "reason":str(exc)[:300],**SAFE})
        exact=sum(t.get("status")=="METEORA_DAMM_V2_OFFICIAL_SIGNED_EXACT" for t in trials)
        reports.append({"pool":pool["pool"],"exact_matches":exact,
                        "trial_count":len(trials),"trials":trials,
                        "verified":exact==4 and len(trials)==4})
    complete=len(reports)==a.pool_count and all(r["verified"] for r in reports)
    report={"status":("METEORA_DAMM_V2_CONFIGURED_POOLS_SIGNED_VERIFIED"
                       if complete else "METEORA_DAMM_V2_CONFIGURED_POOLS_INCOMPLETE"),
            "required_distinct_pools":a.pool_count,
            "verified_pool_count":sum(r["verified"] for r in reports),
            "exact_matches":sum(r["exact_matches"] for r in reports),
            "trial_count":sum(r["trial_count"] for r in reports),
            "pool_selection_blockers":attempts,
            "pools":reports,"protocol_exact_verified":complete,**SAFE}
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],
          "verified_pool_count":report["verified_pool_count"],
          "exact_matches":report["exact_matches"],
          "trial_count":report["trial_count"],**SAFE}))
    if not complete:
        raise SystemExit("six distinct Meteora pool signed prices not yet verified")

if __name__=="__main__":
    main()
