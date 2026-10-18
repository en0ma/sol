"""Read-only offline Surfpool probe for ephemeral signer token accounts.

No funding, account creation, signed chain transactions or broadcasts.
Missing accounts are expected and are reported as explicit blockers.
"""
import json
import os
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

def run(rpc):
    require_loopback_rpc(rpc)
    signer=Keypair()
    addresses=[str(Pubkey.find_program_address(
        [bytes(signer.pubkey()),bytes(Pubkey.from_string(program)),bytes(Pubkey.from_string(mint))],
        Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"))[0])
        for mint,program in (
            ("So11111111111111111111111111111111111111112",
             "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"),
            ("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
             "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"))]
    result=call(rpc,"getMultipleAccounts",[addresses,{"encoding":"base64","commitment":"confirmed"}])
    if not isinstance(result,dict) or not isinstance(result.get("value"),list) or len(result["value"])!=2:
        raise ValueError("malformed offline Surfpool token account evidence")
    present=[account is not None for account in result["value"]]
    return {"status":"BLOCKED_NO_LOCAL_TOKEN_PAIR" if not all(present) else "UNVERIFIED_ACCOUNT_CONTENTS",
            "token_account_presence":present,
            "same_rpc_response":True,
            "signer_controlled_accounts_verified":False,
            "signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}

if __name__=="__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))))
