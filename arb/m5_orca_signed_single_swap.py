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

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--fixture",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--amounts",default="10000,100000")
    a=p.parse_args()
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
