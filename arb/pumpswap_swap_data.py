"""PumpSwap exact-input instruction data encoders from official pump_amm IDL.

Read-only bytes: no account metas, transaction signing or broadcasting. Caller
must independently verify every account in the IDL; these bytes alone do not
constitute a swap builder or executable quote.
"""
SELL_DISC=bytes((51,230,133,164,1,127,131,173))
BUY_EXACT_QUOTE_IN_DISC=bytes((198,46,21,82,180,217,232,112))


def _u64(value):
    if type(value) is not int or not 0 < value < 1 << 64:
        raise ValueError("swap amount must be positive u64")
    return value.to_bytes(8,"little")


def encode_sell(base_amount_in, min_quote_amount_out):
    return SELL_DISC + _u64(base_amount_in) + _u64(min_quote_amount_out)


def encode_buy_exact_quote_in(spendable_quote_in, min_base_amount_out, *, track_volume=None):
    if track_volume is None:
        option=bytes((0,))
    elif type(track_volume) is bool:
        option=bytes((1, int(track_volume)))
    else:
        raise ValueError("invalid OptionBool")
    return (BUY_EXACT_QUOTE_IN_DISC + _u64(spendable_quote_in)
            + _u64(min_base_amount_out) + option)
