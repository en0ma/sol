"""Provision two ephemeral token accounts on an explicitly offline Surfpool RPC.

Offline test setup only: surfnet_setAccount is a local cheatcode, not a
transaction. Never connect this module to the mainnet-fork probe.
"""
import json
import os
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc,observe_token_account
from arb.orca_swap_v2_user_role_binding import bind_local_user_accounts
from arb.orca_swap_v2_metas import ACCOUNT_ROLES, WRITABLE, SIGNERS, MEMO_PROGRAM

TOKEN="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
MINTS=("So11111111111111111111111111111111111111112",
       "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")

def token_account_bytes(mint,authority,amount):
    if type(amount) is not int or not 0<=amount<2**64:
        raise ValueError("invalid offline token amount")
    raw=bytearray(165)
    raw[:32]=bytes(Pubkey.from_string(mint))
    raw[32:64]=bytes(Pubkey.from_string(authority))
    raw[64:72]=amount.to_bytes(8,"little")
    raw[108]=1
    return bytes(raw)

def run(rpc):
    require_loopback_rpc(rpc)
    # This opt-in is enabled only in the --offline smoke-test job.
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE")!="1":
        raise ValueError("offline provisioning must be explicitly enabled")
    signer=Keypair()
    authority=str(signer.pubkey())
    accounts=[str(Keypair().pubkey()),str(Keypair().pubkey())]
    for address,mint,amount in zip(accounts,MINTS,(1000000,2000000)):
        raw=token_account_bytes(mint,authority,amount)
        call(rpc,"surfnet_setAccount",[address,{
            "lamports":2039280,"data":raw.hex(),"owner":TOKEN,"executable":False}])
    observed=[observe_token_account(rpc,account,mint,authority,TOKEN)
              for account,mint in zip(accounts,MINTS)]
    if observed[0]["slot"]!=observed[1]["slot"]:
        raise ValueError("offline account reads not slot-aligned")
    import base64
    snapshot=call(rpc,"getMultipleAccounts",[accounts,{"encoding":"base64","commitment":"confirmed"}])
    slot=snapshot.get("context",{}).get("slot") if isinstance(snapshot,dict) else None
    values=snapshot.get("value") if isinstance(snapshot,dict) else None
    if type(slot) is not int or not isinstance(values,list) or len(values)!=2:
        raise ValueError("missing synchronized offline token account snapshot")
    for i,(value,mint,amount) in enumerate(zip(values,MINTS,(1000000,2000000))):
        if not isinstance(value,dict) or value.get("owner")!=TOKEN:
            raise ValueError("offline token account program owner mismatch")
        data=value.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("offline token account encoding mismatch")
        raw=base64.b64decode(data[0],validate=True)
        if len(raw)<165 or str(Pubkey.from_bytes(raw[:32]))!=mint or str(Pubkey.from_bytes(raw[32:64]))!=authority or raw[108]!=1:
            raise ValueError("offline token account content mismatch")
        if int.from_bytes(raw[64:72],"little")!=amount:
            raise ValueError("offline token account balance mismatch")
    # The readbacks above are real offline RPC observations, not mocked fixtures.
    roles={
        "token_program_a":TOKEN,"token_program_b":TOKEN,
        "memo_program":MEMO_PROGRAM,"token_authority":authority,
        "token_mint_a":MINTS[0],"token_mint_b":MINTS[1],
        "token_owner_account_a":accounts[0],"token_owner_account_b":accounts[1],
    }
    metas=[{"role":role,"address":roles.get(role,"UNVERIFIED_"+role),
            "is_signer":i in SIGNERS,"is_writable":i in WRITABLE}
           for i,role in enumerate(ACCOUNT_ROLES)]
    binding=bind_local_user_accounts(metas,observed[0],observed[1],authority)
    if not binding["local_user_accounts_match_swap_v2_roles"]:
        raise ValueError("local token account role binding failed")
    return {"status":"LOCAL_TEST_ACCOUNTS_CREATED_AND_READ_BACK",
            "account_count":2,"same_context_slot":True,
            "synchronized_balance_snapshot_slot":slot,
            "amounts_verified_base_units":[1000000,2000000],
            "ephemeral_authority_observed":True,
            "swap_v2_user_roles_verified_locally":True,
            "swap_v2_pool_side_accounts_verified":False,
            "signed_swap_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}

if __name__=="__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL","http://127.0.0.1:8899"))))
