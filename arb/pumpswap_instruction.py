"""Construct unsigned PumpSwap exact-input instructions; no sending or signing.

The caller is responsible for fee-recipient authentication and validating
all token accounts. Building bytes is not verification of executability.
"""
from arb.pumpswap_account_metas import account_metas
from arb.pumpswap_swap_data import encode_sell, encode_buy_exact_quote_in
from arb.pumpswap_pool import PROGRAM


def build_instruction(direction, addresses, amount_in, min_out, *, track_volume=None):
    if direction=="sell":
        if track_volume is not None:
            raise ValueError("sell does not accept track_volume")
        data=encode_sell(amount_in,min_out)
    elif direction=="buy_exact_quote_in":
        data=encode_buy_exact_quote_in(amount_in,min_out,track_volume=track_volume)
    else:
        raise ValueError("unsupported PumpSwap swap direction")
    specs=account_metas(direction,addresses)
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    accounts=[AccountMeta(Pubkey.from_string(v["address"]),v["is_signer"],v["is_writable"])
              for v in specs["metas"]]
    return Instruction(Pubkey.from_string(PROGRAM),data,accounts)
