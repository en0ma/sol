"""Signed Orca-only bidirectional execution on a read-only isolated Surfpool fork.

The signed swap output, Orca Core reference and local native quote must agree.
No live broadcast, no assumed Clock, no fabricated pool/ticks.
"""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
from solders.keypair import Keypair
from solders.transaction import Transaction
from solders.hash import Hash
from arb.rpc import call
from arb.next_ten_signed_atomic_offline import hydrate
from arb.source_snapshot_manifest import verify
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.m5_orca_official_core_parity import source_core_inputs
from arb.orca_adaptive_fee_source import quote_adaptive_from_arrays
from arb.orca_fork_clock import fork_clock,stable_orca_fork_clock
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
from arb.venue_swap_adapter import build_leg
from arb.orca_whirlpool import PROGRAM,decode as decode_pool
from arb.damm_cpmm_atomic_offline import _simulate
from arb.pumpswap_local_simulation import local_rpc_only
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
from arb.next_ten_pair_fixture_export import venue_accounts,program_data_accounts
from arb.m5_meteora_damm_v2_dedicated_signed_fork import hydrate as hydrate_program,_balances
from arb.orca_whirlpool import b58
from arb.whirlpool_ticks import FIXED_LEN,DISC,DYNAMIC_DISC,DYNAMIC_MIN_LEN,DYNAMIC_MAX_LEN,decode_fixed_ticks,decode_dynamic_ticks,addresses,start_tick
from arb.orca_adaptive_fee_source import source_oracle
SYSTEM="11111111111111111111111111111111"

def _run(rpc,fixture,direction,amount,binary):
    local_rpc_only(rpc)
    verify(fixture)
    if any(fixture.get(k)is not False for k in SAFE):
        raise ValueError("unsafe source fixture")
    rows=extract_pool_states(fixture)
    indices=[i for i,r in enumerate(rows) if r["venue"]=="orca"]
    if len(indices)!=1 or direction not in ("a_to_b","b_to_a") or type(amount)is not int or not 0<amount<2**64:
        raise ValueError("one Orca pool, direction and u64 amount required")
    i=indices[0]
    down=direction=="a_to_b"
    args=source_core_inputs(fixture,i,specified_token_a=down)
    state=args["pool"]
    pool=rows[i]["address"]
    mint_in=state["token_mint_a" if down else "token_mint_b"]
    mint_out=state["token_mint_b" if down else "token_mint_a"]
    proof=fixture["leg_evidence_by_index"][i]
    if not isinstance(proof.get("auxiliary"),dict):
        raise ValueError("source swap account evidence missing")
    evidence={**proof,**proof["auxiliary"]}
    hydrate(rpc,fixture)
    observed=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])["value"]
    if observed["owner"]!=PROGRAM or decode_pool(base64.b64decode(observed["data"][0],validate=True))!=state:
        raise ValueError("hydrated pool state differs from authenticated fixture")
    signer=Keypair()
    owner=str(signer.pubkey())
    src,dst=str(Keypair().pubkey()),str(Keypair().pubkey())
    call(rpc,"surfnet_setAccount",[owner,{"lamports":1000000000,
         "data":"","owner":"11111111111111111111111111111111","executable":False}])
    for address,mint,balance in ((src,mint_in,amount),(dst,mint_out,0)):
        call(rpc,"surfnet_setAccount",[address,{"lamports":2039280,
             "data":token_account_bytes(mint,owner,balance).hex(),
             "owner":TOKEN_PROGRAM,"executable":False}])
    call(rpc,"surfnet_pauseClock",[])
    try:
        before=fork_clock(rpc)
        ix=build_leg("orca",pool,state,evidence,owner,src,dst,
                     mint_in,mint_out,amount,1)
        blockhash=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],
                                              Hash.from_string(blockhash))
        positive,_=_simulate(rpc,tx,[src,dst])
        if positive.get("err") is not None:
            raise ValueError("signed real Orca program rejected swap: "+str(positive["err"])[:160])
        accounts=positive.get("accounts")
        if not isinstance(accounts,list) or len(accounts)!=2:
            raise ValueError("signed post-simulation SPL token inventory missing")
        balances=[]
        for account,mint in zip(accounts,(mint_in,mint_out)):
            if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
                raise ValueError("untrusted simulated SPL output owner")
            decoded=decode_token_account(base64.b64decode(account["data"][0],validate=True))
            if decoded["mint"]!=mint or decoded["authority"]!=owner:
                raise ValueError("simulated SPL mint/authority mismatch")
            balances.append(decoded["amount_base_units"])
        if balances[0]!=0 or balances[1]<=0:
            raise ValueError("signed Orca exact-input balance delta missing")
        after=fork_clock(rpc)
        clock=stable_orca_fork_clock(before,after)
        if not clock["fork_clock_stable_for_quote"] or before["fork_clock_slot"]!=after["fork_clock_slot"]:
            raise ValueError("fork execution Clock not pinned")
        timestamp=clock["fork_unix_timestamp"]
        core_input={**args,"amount_in":amount,"fork_unix_timestamp":timestamp}
        core=subprocess.run([binary],input=json.dumps(core_input),text=True,
                            capture_output=True,timeout=30)
        if core.returncode:
            raise ValueError("official Orca Core quote failed: "+core.stderr[-200:])
        official=json.loads(core.stdout)["amount_out"]
        native=quote_adaptive_from_arrays(state,mint_in,amount,
            [{**ar,"status":"FIXED_VALID"} for ar in args["arrays"]],
            args["oracle"],observed_unix=timestamp)
        local=native["estimated_output_base_units"]
        signed=balances[1]
        return {"status":("SIGNED_ORCA_THREE_WAY_EXACT" if official==local==signed
                          else "SIGNED_ORCA_THREE_WAY_MISMATCH"),
                "direction":direction,"amount_in":amount,"signed_spl_output":signed,
                "official_core_output":official,"local_native_output":local,
                "source_slot":fixture["state_accounts_observed_slot"],
                "fork_clock":clock,"signed_transaction_sha256":hashlib.sha256(bytes(tx)).hexdigest(),
                "signed_transaction_signature":str(tx.signatures[0]),
                "signed_orca_program_execution":True,**SAFE}
    finally:
        call(rpc,"surfnet_resumeClock",[])

def capture_pool(rpc,pool):
    from arb.next_ten_fork_pool_probe import snapshot
    proof=snapshot(rpc,pool,"orca")
    mints=proof["mints"]
    extra,aux=venue_accounts(rpc,"orca",pool,mints)
    keys=list(dict.fromkeys(extra))
    response=call(rpc,"getMultipleAccounts",[keys,{"encoding":"base64","commitment":"confirmed"}])
    values=response.get("value")
    slot=response.get("context",{}).get("slot")
    if type(slot)is not int or not isinstance(values,list) or any(not isinstance(v,dict) for v in values):
        raise ValueError("Orca source pool+tick/vault accounts not from one slot")
    accounts=dict(zip(keys,values))
    raw=base64.b64decode(accounts[pool]["data"][0],validate=True)
    if accounts[pool]["owner"]!=PROGRAM or accounts[pool].get("executable") is not False:
        raise ValueError("Orca authenticated pool program ownership changed")
    state=decode_pool(raw)
    if set((state["token_mint_a"],state["token_mint_b"]))!=set(mints):
        raise ValueError("Orca source mint identities changed")
    accounts.update(program_data_accounts(rpc,{PROGRAM}))
    if state["tick_spacing"]!=state["fee_tier_index_seed"] and aux.get("oracle") not in accounts:
        raise ValueError("Orca adaptive oracle source unavailable")
    return {"pool":pool,"program":PROGRAM,"state":state,"accounts":accounts,
            "source_slot":slot,"auxiliary":aux,**SAFE}

def export_source(rpc,registry,output,*,pool_count=6,excluded=()):
    selected=[];blockers=[]
    excluded=set(excluded)
    seen=set()
    for row in registry["pools"]:
        if row.get("venue")!="orca":continue
        pool=row["address"]
        if pool in seen or pool in excluded:continue
        seen.add(pool)
        try:
            selected.append(capture_pool(rpc,pool))
            if len(selected)==pool_count:break
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            blockers.append({"pool":pool,"reason":str(exc)[:220]})
    result={"selected_pools":selected,"required_distinct_pools":pool_count,
            "selection_blockers":blockers,**SAFE}
    Path(output).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    return len(selected)==pool_count

def quote_args(captured,direction):
    pool=captured["pool"];state=captured["state"];accounts=captured["accounts"]
    oracle=source_oracle({"leg_evidence_by_index":[{
        "venue":"orca","pool":pool,"auxiliary":captured["auxiliary"]}],
        "state_account_addresses":list(accounts),"accounts":accounts},pool,state)
    spacing=state["tick_spacing"]
    arrays={}
    for addr,info in accounts.items():
        if info.get("owner")!=PROGRAM or info.get("executable") is not False:continue
        raw=base64.b64decode(info["data"][0],validate=True)
        fixed=len(raw)==FIXED_LEN and raw[:8]==DISC
        dynamic=DYNAMIC_MIN_LEN<=len(raw)<=DYNAMIC_MAX_LEN and raw[:8]==DYNAMIC_DISC
        if not (fixed or dynamic):continue
        parent=b58(raw[-32:]) if fixed else b58(raw[12:44])
        if parent!=pool:continue
        start=int.from_bytes(raw[8:12],"little",signed=True)
        if start in arrays or addresses(pool,[start])[0]!=addr:
            raise ValueError("Orca source array duplicate or forged PDA")
        ticks=decode_fixed_ticks(raw,pool,start,spacing) if fixed else decode_dynamic_ticks(raw,pool,start,spacing)
        arrays[start]={"start_tick":start,"ticks":ticks}
    down=direction=="a_to_b"
    current=start_tick(state["tick_current_index"],spacing)
    ordered=[]
    while current in arrays and len(ordered)<6:
        ordered.append(arrays[current])
        current+=(-88 if down else 88)*spacing
    if not ordered:
        raise ValueError("missing Orca authenticated directional ticks")
    return {"pool":state,"oracle":oracle,"arrays":ordered,
            "specified_token_a":down}

def _run_new_pool(rpc,captured,direction,amount,binary):
    local_rpc_only(rpc)
    state=captured["state"];pool=captured["pool"]
    down=direction=="a_to_b"
    mint_in=state["token_mint_a" if down else "token_mint_b"]
    mint_out=state["token_mint_b" if down else "token_mint_a"]
    args=quote_args(captured,direction)
    signer=Keypair();owner=str(signer.pubkey())
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
        evidence={"venue":"orca","pool":pool,**captured["auxiliary"]}
        ix=build_leg("orca",pool,state,evidence,owner,src,dst,mint_in,mint_out,amount,1)
        blockhash=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])["value"]["blockhash"]
        tx=Transaction.new_signed_with_payer([ix],signer.pubkey(),[signer],Hash.from_string(blockhash))
        positive,_=_simulate(rpc,tx,[src,dst])
        if positive.get("err") is not None:
            raise ValueError("Orca signed swap rejected: "+str(positive["err"])[:220])
        balances=_balances(positive,(mint_in,mint_out),owner)
        if balances[0]!=0 or balances[1]<=0:
            raise ValueError("Orca signed SPL exact input not observed")
        after=fork_clock(rpc)
        clock=stable_orca_fork_clock(before,after)
        if not clock["fork_clock_stable_for_quote"] or before["fork_clock_slot"]!=after["fork_clock_slot"]:
            raise ValueError("unstable signed Orca clock")
        timestamp=clock["fork_unix_timestamp"]
        official=subprocess.run([binary],input=json.dumps({**args,"amount_in":amount,
                              "fork_unix_timestamp":timestamp}),
                              text=True,capture_output=True,timeout=40)
        if official.returncode:
            raise ValueError("official Orca Core refused source: "+official.stderr[-250:])
        core=json.loads(official.stdout)["amount_out"]
        native=quote_adaptive_from_arrays(state,mint_in,amount,
            [{**array,"status":"FIXED_VALID"} for array in args["arrays"]],
            args["oracle"],observed_unix=timestamp)["estimated_output_base_units"]
        signed=balances[1]
        return {"status":"ORCA_NEW_POOL_SIGNED_EXACT" if signed==core==native else "ORCA_NEW_POOL_MISMATCH",
                "pool":pool,"direction":direction,"input":amount,
                "signed_spl_output":signed,"official_core_output":core,
                "local_native_output":native,"fork_clock":clock,
                "signed_sha256":hashlib.sha256(bytes(tx)).hexdigest(),**SAFE}
    finally:
        call(rpc,"surfnet_resumeClock",[])


def new_pool_main(a):
    rpc="http://127.0.0.1:8899"
    if a.capture_new_pools:
        if not a.registry or not a.new_pools_source:
            raise SystemExit("new-pool capture needs authenticated venue registry")
        report=json.loads(Path(a.registry).read_text())
        if not export_source(rpc,report,a.new_pools_source,
                             pool_count=a.pool_count):
            raise SystemExit("insufficient authenticated Orca source pools")
        return
    captured=json.loads(Path(a.new_pools_source).read_text()).get("selected_pools",[])
    if len(captured)!=a.pool_count or len({p["pool"] for p in captured})!=a.pool_count:
        raise SystemExit("distinct authenticated Orca pool fixtures required")
    reports=[]
    for pool in captured:
        receipts=[]
        try:
            hydrate_program(rpc,pool,program=PROGRAM)
            for direction in ("a_to_b","b_to_a"):
                for size in (int(x) for x in a.amounts.split(",")):
                    try:
                        receipts.append(_run_new_pool(rpc,pool,direction,size,a.binary))
                    except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                        receipts.append({"status":"SIGNED_ORCA_DIRECTION_UNVERIFIED",
                           "reason":str(exc)[:300],"direction":direction,"amount_in":size,**SAFE})
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            receipts.append({"status":"SIGNED_ORCA_HYDRATION_UNVERIFIED",
                             "reason":str(exc)[:300],**SAFE})
        exact=sum(x.get("status")=="ORCA_NEW_POOL_SIGNED_EXACT" for x in receipts)
        reports.append({"pool":pool["pool"],"exact":exact,
                        "trials":receipts,"verified":exact==4 and len(receipts)==4})
    verified=sum(x["verified"] for x in reports)
    required=a.required_verified_pools
    report={"status":"ORCA_NEW_POOLS_SIGNED_VERIFIED" if verified>=required
                  else "ORCA_NEW_POOLS_SIGNED_INCOMPLETE",
            "verified_pool_count":verified,"required_verified_pools":required,
            "candidate_count":len(reports),"pools":reports,**SAFE}
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],
          "verified_pool_count":verified,"candidate_count":len(reports),**SAFE}))
    if verified<required:
        raise SystemExit("six new Orca source pool pricing checks not yet verified")

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture")
    p.add_argument("--registry")
    p.add_argument("--new-pools-source")
    p.add_argument("--capture-new-pools",action="store_true")
    p.add_argument("--pool-count",type=int,default=8)
    p.add_argument("--required-verified-pools",type=int,default=6)
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amounts",default="10000,100000")
    a=p.parse_args()
    if a.new_pools_source:
        new_pool_main(a)
        return
    if not a.fixture:
        raise SystemExit("existing Orca fixture required")
    fixture=json.loads(Path(a.fixture).read_text())
    trials=[]
    for direction in ("a_to_b","b_to_a"):
        for n in a.amounts.split(","):
            amount=int(n)
            try:
                result=_run("http://127.0.0.1:8899",fixture,direction,amount,a.binary)
            except (ValueError,TypeError,KeyError,RuntimeError,OSError) as e:
                result={"status":"SIGNED_ORCA_DIRECTION_UNVERIFIED","direction":direction,
                        "amount_in":amount,"reason":str(e)[:350],**SAFE}
            trials.append(result)
    matched=sum(x["status"]=="SIGNED_ORCA_THREE_WAY_EXACT" for x in trials)
    report={"status":("ORCA_SIGNED_BOTH_DIRECTIONS_EXACT" if matched==len(trials)
                      else "ORCA_SIGNED_BOTH_DIRECTIONS_NOT_PROVEN"),
            "matched":matched,"attempted":len(trials),"trials":trials,**SAFE}
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"matched":matched,
                      "attempted":len(trials),**SAFE}))
    if matched!=len(trials):
        raise SystemExit("signed fork Orca bidirectional parity incomplete")

if __name__=="__main__":
    main()
