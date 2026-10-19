"""Offline negative-control signed SwapV2 simulation with deliberately absent pool.

This establishes that a real signed Orca instruction is rejected without
verified pool accounts. No mainnet calls, no sendTransaction and no approval.
"""
import base64
import json
import os
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_metas import ACCOUNT_ROLES,WRITABLE,SIGNERS,MEMO_PROGRAM
from arb.orca_swap_v2_candidate import unsigned_swap_v2_candidate

def require_pool_rejection_error(error):
    """Reject transport/runtime failures that never establish Orca pool validation."""
    error_text=str(error)
    if any(reason in error_text.lower() for reason in (
            "blockhashnotfound","signaturefailure","signature verification",
            "insufficientfundsforfee","invalidprogramforexecution",
            "programaccountnotfound","accountnotfound")):
        raise ValueError("SwapV2 rejected before pool validation: "+error_text)
    return error_text

def run(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("requires explicitly offline Surfpool")
    signer=Keypair()
    call(rpc,"surfnet_setAccount",[str(signer.pubkey()),{
        "lamports":1000000000,"data":"","owner":"11111111111111111111111111111111",
        "executable":False}])
    metas=[{"role":role,
            "address":MEMO_PROGRAM if role=="memo_program" else
                      str(signer.pubkey()) if role=="token_authority" else
                      str(Keypair().pubkey()),
            "is_signer":i in SIGNERS,"is_writable":i in WRITABLE}
           for i,role in enumerate(ACCOUNT_ROLES)]
    candidate=unsigned_swap_v2_candidate(metas,1000,1,2**64,True,True)
    latest=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])
    tx=Transaction.new_signed_with_payer(
        [candidate["instruction"]],signer.pubkey(),[signer],
        Hash.from_string(latest["value"]["blockhash"]))
    result=call(rpc,"simulateTransaction",[
        base64.b64encode(bytes(tx)).decode(),
        {"encoding":"base64","sigVerify":True,
         "replaceRecentBlockhash":False,"commitment":"confirmed"}])
    value=result.get("value") if isinstance(result,dict) else None
    if not isinstance(value,dict) or value.get("err") is None:
        raise ValueError("unverified SwapV2 negative-control unexpectedly succeeded")
    error_text=require_pool_rejection_error(value["err"])
    return {"status":"SWAP_V2_NEGATIVE_CONTROL_REJECTED",
            "observed_simulation_error":error_text,
            "signature_verification_requested":True,
            "rejected":True,"signed_swap_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}

if __name__=="__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))))
