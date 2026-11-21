"""Diagnostic-only binding of an ephemeral signer to two local token accounts.

Caller supplies a fresh in-memory keypair and local-fork account addresses.
No transaction construction, signing for the chain, or broadcasting occurs.
"""
import os
from solders.keypair import Keypair
from arb.orca_swap_v2_local_token_accounts import observe_token_account, require_loopback_rpc

DOMAIN=b"sol-surfpool-orca-token-owner-binding-v1:"

def observe_ephemeral_token_pair(rpc,signer,account_a,mint_a,program_a,
                                 account_b,mint_b,program_b,min_context_slot=None):
    require_loopback_rpc(rpc)
    if not isinstance(signer,Keypair):
        raise ValueError("test signer must be an in-memory keypair")
    if account_a==account_b or mint_a==mint_b:
        raise ValueError("distinct token accounts and mints required")
    challenge=DOMAIN+os.urandom(32)
    signature=signer.sign_message(challenge)
    if not signature.verify(signer.pubkey(),challenge):
        raise ValueError("ephemeral signer challenge failed")
    authority=str(signer.pubkey())
    a=observe_token_account(rpc,account_a,mint_a,authority,program_a,min_context_slot)
    b=observe_token_account(rpc,account_b,mint_b,authority,program_b,min_context_slot)
    if a["slot"]!=b["slot"]:
        raise ValueError("local token account context slots differ")
    if not a["local_rpc_verified"] or not b["local_rpc_verified"]:
        raise ValueError("local account verification incomplete")
    return {"authority":authority,"token_account_a":account_a,
            "token_account_b":account_b,"slot":a["slot"],
            "ephemeral_signer_challenge_verified":True,
            "token_accounts_verified_same_slot":True,
            "quote_and_pool_same_fork_verified":False,
            "signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}
