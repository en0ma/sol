"""Orca Whirlpool legacy swap instruction constructor (simulation only).

Account order and args follow Orca's on-chain swap program, not any DEX API.
Does NOT infer execution viability from spot prices. Never submits transactions.
Requires supplied funded SPL token accounts and an independently validated oracle.
"""
import hashlib
from arb.orca_whirlpool import PROGRAM
from arb.whirlpool_ticks import start_tick, addresses
from arb.token_vaults import TOKEN_PROGRAM

DISC = hashlib.sha256(b"global:swap").digest()[:8]
MIN_SQRT = 4295048016
MAX_SQRT = 79226673515401279992447579055

def encode_swap(amount, other_amount_threshold, sqrt_price_limit,
                amount_specified_is_input=True, a_to_b=True):
    for name,value,bits in (("amount",amount,64),("threshold",other_amount_threshold,64),
                            ("sqrt price limit",sqrt_price_limit,128)):
        if type(value) is not int or value < 0 or value >= 1 << bits:
            raise ValueError("invalid "+name)
    if amount == 0 or not (MIN_SQRT <= sqrt_price_limit <= MAX_SQRT):
        raise ValueError("amount must be positive and sqrt limit in valid range")
    if type(amount_specified_is_input) is not bool or type(a_to_b) is not bool:
        raise TypeError("swap flags must be bool")
    return (DISC + amount.to_bytes(8,"little") +
            other_amount_threshold.to_bytes(8,"little") +
            sqrt_price_limit.to_bytes(16,"little") +
            bytes([amount_specified_is_input,a_to_b]))

def select_tick_arrays(pool_address, current_tick, spacing, a_to_b):
    first = start_tick(current_tick,spacing)
    step = -88*spacing if a_to_b else 88*spacing
    starts = [first, first+step, first+step*2]
    # Whirlpool requires three sequential arrays in trade direction.
    # The first may need a shifted start at exact negative boundaries:
    # correctness must ultimately be confirmed by simulation.
    return addresses(pool_address,starts)

def build_swap(pool_address, state, user_authority, user_account_a,
               user_account_b, oracle, amount, min_output, a_to_b=True,
               sqrt_price_limit=None, amount_specified_is_input=True, oracle_writable=False):
    """Return solders Instruction; caller must prepare user token accounts."""
    from solders.instruction import AccountMeta, Instruction
    from solders.pubkey import Pubkey
    if type(oracle_writable) is not bool:
        raise ValueError("oracle mutability flag must be boolean")
    if sqrt_price_limit is None:
        sqrt_price_limit = MIN_SQRT if a_to_b else MAX_SQRT
    current = int(state["sqrt_price_x64"])
    if not (MIN_SQRT <= sqrt_price_limit < current if a_to_b
            else current < sqrt_price_limit <= MAX_SQRT):
        raise ValueError("invalid price limit direction")
    tick_arrays = select_tick_arrays(pool_address,state["tick_current_index"],
                                    state["tick_spacing"],a_to_b)
    def meta(key, writable=False, signer=False):
        return AccountMeta(Pubkey.from_string(key),signer,writable)
    keys = [meta(TOKEN_PROGRAM),meta(user_authority,signer=True),
            meta(pool_address,writable=True),meta(user_account_a,writable=True),
            meta(state["token_vault_a"],writable=True),
            meta(user_account_b,writable=True),
            meta(state["token_vault_b"],writable=True),
            *(meta(k,writable=True) for k in tick_arrays),
            meta(oracle,writable=oracle_writable)]
    payload = encode_swap(amount,min_output,sqrt_price_limit,amount_specified_is_input,a_to_b)
    return Instruction(Pubkey.from_string(PROGRAM),payload,keys)

def inspect_swap_requirements(rpc,pool_address):
    """Account-readiness report: no signer private keys required."""
    from arb.whirlpool_ticks import inspect
    r=inspect(rpc,pool_address)
    valid = {a["start_tick"]:a for a in r["arrays"] if a["status"]=="FIXED_VALID"}
    spacing = None
    from arb.orca_whirlpool import fetch_pool
    state=fetch_pool(rpc,pool_address)
    directions={}
    for a_to_b in (True,False):
        first=start_tick(state["tick_current_index"],state["tick_spacing"])
        span=88*state["tick_spacing"]*(-1 if a_to_b else 1)
        indexes=[first+i*span for i in range(3)]
        directions["a_to_b" if a_to_b else "b_to_a"]={
            "required_starts":indexes,
            "available":all(i in valid for i in indexes)}
    return {"pool":pool_address,"directions":directions,
            "user_token_accounts_ready":False,
            "swap_simulated":False,
            "note":"Instruction encoder available; funded user accounts and oracle required"}
