"""Diagnostic-only Orca SwapV2 instruction-data encoder (no signing or RPC).

Borsh format: discriminator, u64 amount, u64 threshold, u128 price limit,
two bools, Option<RemainingAccountsInfo>. Only None is supported until
TransferHook/supplemental account slices have been validated.
"""
import hashlib

DISCRIMINATOR=hashlib.sha256(b"global:swap_v2").digest()[:8]

def encode_swap_v2_data(amount,other_amount_threshold,sqrt_price_limit,
                        amount_specified_is_input,a_to_b,remaining_accounts_info=None):
    if remaining_accounts_info is not None:
        raise ValueError("SwapV2 remaining accounts not yet supported")
    for name,value,bits in (
        ("amount",amount,64),("other_amount_threshold",other_amount_threshold,64),
        ("sqrt_price_limit",sqrt_price_limit,128)):
        if type(value) is not int or not 0<=value<2**bits:
            raise ValueError("invalid SwapV2 "+name)
    if amount==0 or sqrt_price_limit==0:
        raise ValueError("zero SwapV2 amount or sqrt price limit")
    if type(amount_specified_is_input) is not bool or type(a_to_b) is not bool:
        raise ValueError("SwapV2 direction and amount mode must be bool")
    return (DISCRIMINATOR+amount.to_bytes(8,"little")+
            other_amount_threshold.to_bytes(8,"little")+
            sqrt_price_limit.to_bytes(16,"little")+
            bytes((int(amount_specified_is_input),int(a_to_b),0)))
