"""Bind verified offline token accounts to SwapV2 user-account roles.

Diagnostic only: this does not verify a Whirlpool or produce a signed swap.
"""
from arb.orca_swap_v2_metas import ACCOUNT_ROLES

def bind_local_user_accounts(metas,token_a,token_b,signer_pubkey):
    if not isinstance(metas,(list,tuple)) or len(metas)!=len(ACCOUNT_ROLES):
        raise ValueError("invalid SwapV2 account layout")
    if not isinstance(signer_pubkey,str) or not signer_pubkey:
        raise ValueError("missing signer identity")
    for entry,role in zip(metas,ACCOUNT_ROLES):
        if not isinstance(entry,dict) or entry.get("role")!=role:
            raise ValueError("SwapV2 account ordering mismatch")
    if not isinstance(token_a,dict) or not isinstance(token_b,dict):
        raise ValueError("missing local token-account evidence")
    if (token_a.get("authority")!=signer_pubkey or token_b.get("authority")!=signer_pubkey
            or not token_a.get("local_rpc_verified") or not token_b.get("local_rpc_verified")):
        raise ValueError("token authority or local readback unverified")
    if (type(token_a.get("slot")) is not int or token_a["slot"]!=token_b.get("slot")):
        raise ValueError("local token accounts not observed at same slot")
    for index,token in ((7,token_a),(9,token_b)):
        if metas[index].get("address")!=token.get("account"):
            raise ValueError("SwapV2 owner token account mismatch")
    if metas[3].get("address")!=signer_pubkey or not metas[3].get("is_signer"):
        raise ValueError("SwapV2 signing authority mismatch")
    for index,token in ((0,token_a),(1,token_b)):
        if metas[index].get("address")!=token.get("token_program"):
            raise ValueError("SwapV2 token program mismatch")
    for index,token in ((5,token_a),(6,token_b)):
        if metas[index].get("address")!=token.get("mint"):
            raise ValueError("SwapV2 token mint mismatch")
    return {"local_user_accounts_match_swap_v2_roles":True,
            "user_account_snapshot_slot":token_a["slot"],
            "pool_and_quote_same_fork_verified":False,
            "signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}
