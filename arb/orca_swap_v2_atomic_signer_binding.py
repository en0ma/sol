"""Bind an in-memory ephemeral signer to one synchronized Whirlpool account read.

Read-only. Never accepts a serialized private key, creates accounts or broadcasts.
Signer possession plus account readback is not SwapV2 execution authorization.
"""
import os
from solders.keypair import Keypair
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_atomic_pool_user_readback import observe_atomic_pool_user_identities

DOMAIN = b"sol-surfpool-orca-atomic-pool-user-signer-v1:"

def observe_signed_pool_user_binding(rpc, plan, addresses, signer):
    require_loopback_rpc(rpc)
    if not isinstance(signer, Keypair):
        raise ValueError("ephemeral in-memory signer required")
    challenge = DOMAIN + os.urandom(32)
    signature = signer.sign_message(challenge)
    if not signature.verify(signer.pubkey(), challenge):
        raise ValueError("signer challenge signature verification failed")
    authority = str(signer.pubkey())
    evidence = observe_atomic_pool_user_identities(rpc, plan, addresses, authority)
    if (evidence.get("same_context_pool_user_identities_verified") is not True or
            evidence.get("same_context_vault_mint_programs_verified") is not True or
            evidence.get("user_token_accounts") != list(addresses)):
        raise ValueError("pool and signer-owned user account identities not verified")
    return {
        "status": "EPHEMERAL_SIGNER_POOL_USER_BINDING_VERIFIED",
        "signer_authority": authority,
        "ephemeral_signer_challenge_verified": True,
        "same_context_pool_user_identities_verified": True,
        "observation_slot": evidence["observation_slot"],
        "user_token_accounts": evidence["user_token_accounts"],
        "observed_balances_base_units": evidence["observed_balances_base_units"],
        "same_context_vault_mint_programs_verified": True,
        "full_swap_account_set_verified": False,
        "signed_simulation_verified": False,
        "actionable": False, "executable_quote": False, "broadcast": False,
    }
