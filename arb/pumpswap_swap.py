"""PumpSwap buy_v2/sell_v2 instruction builders pinned to official pump_amm IDL.

Buy is exact BASE output with max QUOTE input; sell is exact BASE input
with minimum QUOTE output. They are NOT interchangeable exact-input swaps.
Account addresses must be independently authenticated against the pool and
fee config before signed simulation. No live execution or broadcast.
"""
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_global_config import ADDRESS as GLOBAL_CONFIG
from arb.pumpswap_fee_account import ADDRESS as FEE_CONFIG
from arb.token_vaults import TOKEN_PROGRAM

BUY_V2=bytes([184,23,238,97,103,197,211,61])
SELL_V2=bytes([93,246,130,60,231,233,64,178])
SYSTEM="11111111111111111111111111111111"
# The program IDL requires a separate fee-config account owned by pump_fees.
def build_swap_v2(pool,state,user,user_base,user_quote,user_volume_accumulator,
                  buyback_fee_recipient,amount_0,amount_1,*,buy):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    if type(buy)is not bool or any(type(n)is not int or not 0<n<(1<<64) for n in (amount_0,amount_1)):
        raise ValueError("PumpSwap direction and nonzero u64 amounts required")
    if state.get("is_mayhem_mode") not in (0,1) or state.get("is_cashback_coin") not in (0,1):
        raise ValueError("PumpSwap pool flags not authenticated")
    if user_base==user_quote or user_base in (state["base_vault"],state["quote_vault"]) or user_quote in (state["base_vault"],state["quote_vault"]):
        raise ValueError("PumpSwap user token accounts invalid")
    program=Pubkey.from_string(PROGRAM)
    event=str(Pubkey.find_program_address([b"__event_authority"],program)[0])
    names=[
        (pool,False,True),(user,True,True),(GLOBAL_CONFIG,False,False),
        (state["base_mint"],False,False),(state["quote_mint"],False,False),
        (user_base,False,True),(user_quote,False,True),
        (state["base_vault"],False,True),(state["quote_vault"],False,True),
        (TOKEN_PROGRAM,False,False),(TOKEN_PROGRAM,False,False),
        (SYSTEM,False,False),(user_volume_accumulator,False,True),
        (FEE_CONFIG,False,False),(buyback_fee_recipient,False,True),
        (event,False,False),(PROGRAM,False,False)]
    metas=[AccountMeta(Pubkey.from_string(a),signer,writable)
           for a,signer,writable in names]
    data=(BUY_V2 if buy else SELL_V2)+amount_0.to_bytes(8,"little")+amount_1.to_bytes(8,"little")
    return Instruction(program,data,metas)
