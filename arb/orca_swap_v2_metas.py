"""Reference SwapV2 account layout; never authorizes or broadcasts a swap.

Indices follow Orca's generated SwapV2 client. This module checks metadata
shape only and cannot prove mint ownership, signer control, or executable state.
"""
ACCOUNT_ROLES=(
    "token_program_a","token_program_b","memo_program","token_authority",
    "whirlpool","token_mint_a","token_mint_b","token_owner_account_a",
    "token_vault_a","token_owner_account_b","token_vault_b",
    "tick_array_0","tick_array_1","tick_array_2","oracle",
)
WRITABLE=frozenset((4,7,8,9,10,11,12,13,14))
SIGNERS=frozenset((3,))
MEMO_PROGRAM="MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"

def validate_swap_v2_metas(metas):
    """Fail closed on incorrect ordering, flags, absent or duplicate accounts."""
    if not isinstance(metas,(tuple,list)) or len(metas)!=len(ACCOUNT_ROLES):
        raise ValueError("SwapV2 requires exactly 15 fixed accounts")
    addresses=[]
    for i,meta in enumerate(metas):
        if not isinstance(meta,dict) or meta.get("role")!=ACCOUNT_ROLES[i]:
            raise ValueError("SwapV2 account role ordering mismatch")
        address=meta.get("address")
        if not isinstance(address,str) or not address:
            raise ValueError("missing SwapV2 account address")
        if type(meta.get("is_writable")) is not bool or meta["is_writable"]!=(i in WRITABLE):
            raise ValueError("SwapV2 writable flag mismatch")
        if type(meta.get("is_signer")) is not bool or meta["is_signer"]!=(i in SIGNERS):
            raise ValueError("SwapV2 signer flag mismatch")
        addresses.append(address)
    if addresses[2]!=MEMO_PROGRAM:
        raise ValueError("unexpected memo program")
    for a,b in ((5,6),(7,9),(8,10),(11,12),(11,13),(12,13)):
        if addresses[a]==addresses[b]:
            raise ValueError("duplicate incompatible SwapV2 account addresses")
    return {"layout_matches_reference":True,"account_count":15,
            "onchain_accounts_verified":False,"signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}
