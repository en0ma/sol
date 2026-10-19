"""Signed local-only transaction simulation transport check (not a swap).

Uses ephemeral key and Memo instruction; never calls sendTransaction.
"""
import base64
import json
import os
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_metas import MEMO_PROGRAM

def run(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("signed simulation requires explicit offline mode")
    signer=Keypair()
    latest=call(rpc,"getLatestBlockhash",[{"commitment":"confirmed"}])
    blockhash=Hash.from_string(latest["value"]["blockhash"])
    instruction=Instruction(Pubkey.from_string(MEMO_PROGRAM),
                            b"surfpool-local-signed-transport-only",
                            [AccountMeta(signer.pubkey(),True,False)])
    tx=Transaction.new_signed_with_payer([instruction],signer.pubkey(),[signer],blockhash)
    result=call(rpc,"simulateTransaction",[
        base64.b64encode(bytes(tx)).decode(),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "commitment":"confirmed"}])
    value=result.get("value") if isinstance(result,dict) else None
    if not isinstance(value,dict) or value.get("err") is not None:
        raise ValueError("offline signed memo simulation failed: "+str(value.get("err") if isinstance(value,dict) else result))
    return {"status":"OFFLINE_SIGNED_MEMO_SIMULATED",
            "signature_verification_requested":True,
            "simulation_error":None,
            "orca_swap_v2_simulated":False,
            "actionable":False,"executable_quote":False,
            "simulation_verified":False,"broadcast":False}

if __name__=="__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))))
