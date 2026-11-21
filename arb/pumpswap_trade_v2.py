"""PumpSwap V2 exact-input instructions from pump-public-docs trade V2 IDL.

17 account metas, no v1 buyback remaining-account list. Requires an
authenticated buyback recipient ATA and signed offline execution for proof.
"""
import hashlib
from arb.pumpswap_pool import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM
from arb.pumpswap_account_resolver import SYSTEM

ORDER=("pool","user","global_config","base_mint","quote_mint",
       "user_base_token_account","user_quote_token_account",
       "pool_base_token_account","pool_quote_token_account",
       "base_token_program","quote_token_program","system_program",
       "user_volume_accumulator","fee_config","buyback_fee_recipient",
       "event_authority","program")
WRITABLE={"pool","user","user_base_token_account","user_quote_token_account",
          "pool_base_token_account","pool_quote_token_account",
          "user_volume_accumulator","buyback_fee_recipient"}

def build_v2(direction,addresses,amount_in,min_out):
    if direction not in ("sell","buy_exact_quote_in"):
        raise ValueError("unsupported PumpSwap V2 direction")
    if any(type(n) is not int or not 0<n<2**64 for n in (amount_in,min_out)):
        raise ValueError("invalid PumpSwap V2 exact-input bounds")
    if (addresses.get("program")!=PROGRAM or
            addresses.get("base_token_program")!=TOKEN_PROGRAM or
            addresses.get("quote_token_program")!=TOKEN_PROGRAM or
            addresses.get("system_program")!=SYSTEM or
            addresses.get("buyback_fee_recipient_authenticated") is not True):
        raise ValueError("unauthenticated PumpSwap V2 fee or program account")
    from solders.instruction import Instruction,AccountMeta
    from solders.pubkey import Pubkey
    metas=[]
    for role in ORDER:
        addr=addresses.get(role)
        if not isinstance(addr,str) or not addr:
            raise ValueError("PumpSwap V2 account missing: "+role)
        metas.append(AccountMeta(Pubkey.from_string(addr),
                    role=="user",role in WRITABLE))
    tag="sell_v2" if direction=="sell" else "buy_exact_quote_in_v2"
    data=(hashlib.sha256(("global:"+tag).encode()).digest()[:8]+
          amount_in.to_bytes(8,"little")+min_out.to_bytes(8,"little"))
    return Instruction(Pubkey.from_string(PROGRAM),data,metas)
