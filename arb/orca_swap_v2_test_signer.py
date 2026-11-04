"""Ephemeral signer challenge for Surfpool-only identity evidence.

Proves local possession of a freshly generated test keypair. Does not verify
token ownership or authorize submitting any transaction.
"""
from solders.keypair import Keypair
from solders.signature import Signature
from solders.pubkey import Pubkey
import os

DOMAIN=b"sol-surfpool-orca-swap-v2-ephemeral-signer-v1:"

def prove_ephemeral_signer_control():
    challenge=DOMAIN+os.urandom(32)
    signer=Keypair()
    signature=signer.sign_message(challenge)
    verified=signature.verify(signer.pubkey(),challenge)
    if not verified:
        raise ValueError("local challenge signature verification failed")
    return {"signer_pubkey":str(signer.pubkey()),
            "challenge_signature_verified":True,
            "ephemeral_test_key_only":True,
            "associated_token_accounts_verified":False,
            "fork_slot_verified":False,
            "signed_swap_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}
