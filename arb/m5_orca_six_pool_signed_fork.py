"""Six NEW Whirlpool pools: signed fork SPL vs official Orca Core vs local native math.

Source capture runs on upstream-backed Surfpool; signing runs only after
rehydrating authentic pool/tick/oracle/program data on an isolated offline fork.
"""
import argparse,base64,hashlib,json,subprocess
from pathlib import Path
from solders.keypair import Keypair
from solders.hash import Hash
from solders.transaction import Transaction
from arb.rpc import call
from arb.next_ten_pair_fixture_export import venue_accounts,program_data_accounts
from arb.meteora_damm_v2_dedicated_signed_fork import hydrate as hydrate_program, _balances
from arb.orca_whirlpool import PROGRAM,decode as decode_pool,b58
from arb.whirlpool_ticks import FIXED_LEN,DISC,DYNAMIC_DISC,DYNAMIC_MIN_LEN,DYNAMIC_MAX_LEN,decode_fixed_ticks,decode_dynamic_ticks,addresses,start_tick
from arb.orca_adaptive_fee_source import source_oracle,quote_adaptive_from_arrays
from arb.orca_fork_clock import fork_clock,stable_orca_fork_clock
from arb.orca_swap_v2_offline_provision import token_account_bytes
from arb.token_vaults import TOKEN_PROGRAM
from arb.venue_swap_adapter import build_leg
from arb.damm_cpmm_atomic_offline import _simulate
from arb.pumpswap_local_simulation import local_rpc_only
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
SYSTEM="11111111111111111111111111111111"

def capture(rpc,pool):
    extra,aux=venue_accounts(rpc,"orca",pool,[])
    # The helper checks pool mint identities: re-fetch decoded mints first.
    return extra,aux

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
    if state["tick_spacing"]==state["fee_tier_index_seed"]:
        raise ValueError("six additional pools must use native adaptive fee")
    accounts.update(program_data_accounts(rpc,{PROGRAM}))
    if aux.get("oracle") not in accounts:
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

def trial(rpc,captured,direction,amount,binary):
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

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--capture-source",action="store_true")
    p.add_argument("--registry")
    p.add_argument("--exclude-fixture")
    p.add_argument("--source-file",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--pool-count",type=int,default=6)
    p.add_argument("--amounts",default="10000,100000")
    a=p.parse_args()
    rpc="http://127.0.0.1:8899"
    if a.capture_source:
        if not a.registry:raise SystemExit("Orca new-pool capture requires registry")
        excluded=[]
        if a.exclude_fixture and Path(a.exclude_fixture).exists():
            fixture=json.loads(Path(a.exclude_fixture).read_text())
            excluded=[pool for venue,pool in zip(fixture.get("route_venues",[]),
                fixture.get("route_pool_addresses",[])) if venue=="orca"]
        okay=export_source(rpc,json.loads(Path(a.registry).read_text()),
                           a.source_file,pool_count=a.pool_count,excluded=excluded)
        if not okay:raise SystemExit("six NEW authentic Orca adaptive pools not captured")
        return
    source=json.loads(Path(a.source_file).read_text())
    pools=source.get("selected_pools",[])
    if len(pools)!=a.pool_count or len({x["pool"] for x in pools})!=a.pool_count:
        raise SystemExit("six independent Orca pool fixtures required")
    results=[]
    for pool in pools:
        trials=[]
        try:
            # Reuse the identical verified upgradeable ELF hydration path.
            hydration={**pool,"accounts":pool["accounts"]}
            hydrate_program(rpc,hydration,program=PROGRAM)
            for direction in ("a_to_b","b_to_a"):
                for amount in (int(x) for x in a.amounts.split(",")):
                    try:
                        trials.append(trial(rpc,pool,direction,amount,a.binary))
                    except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
                        trials.append({"status":"ORCA_NEW_POOL_SIGNED_BLOCKED",
                          "direction":direction,"input":amount,"reason":str(exc)[:280],**SAFE})
        except (ValueError,TypeError,KeyError,RuntimeError,OSError) as exc:
            trials.append({"status":"ORCA_NEW_POOL_HYDRATION_BLOCKED","reason":str(exc)[:280],**SAFE})
        matches=sum(t.get("status")=="ORCA_NEW_POOL_SIGNED_EXACT" for t in trials)
        results.append({"pool":pool["pool"],"matches":matches,"trials":trials,
                        "verified":matches==4 and len(trials)==4})
    verified=sum(r["verified"] for r in results)
    report={"status":"ORCA_SIX_NEW_POOLS_SIGNED_VERIFIED" if verified==a.pool_count
                      else "ORCA_SIX_NEW_POOLS_SIGNED_UNVERIFIED",
            "verified_pool_count":verified,"required_distinct_pools":a.pool_count,
            "pools":results,"protocol_exact_verified":verified==a.pool_count,**SAFE}
    Path(a.output).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":report["status"],"verified_pool_count":verified,**SAFE}))
    if verified!=a.pool_count:raise SystemExit("six new Orca signed native pool prices not proven")

if __name__=="__main__":main()
