"""Meteora DAMM v2 swap2 exact-input instruction builder.

Account order and discriminator pinned to MeteoraAg/damm-v2-sdk
src/idl/cp_amm.json. Instruction construction ONLY, not execution approval.
Classic SPL pools only; caller must authenticate pool/vaults and quote.
"""
from arb.meteora_damm_v2 import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM

SWAP2_DISCRIMINATOR=bytes([65,75,63,76,235,91,91,136])
POOL_AUTHORITY="HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC"

def build_swap2(pool,state,payer,user_input,user_output,amount_in,min_amount_out,
                *,input_is_a,referral_token_account=None):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    if type(input_is_a)is not bool:
        raise ValueError("DAMM v2 input direction must be explicit")
    if any(type(n)is not int or not 0<n<(1<<64) for n in (amount_in,min_amount_out)):
        raise ValueError("nonzero DAMM v2 exact-input and output threshold required")
    if state.get("pool_status")!=0 or state.get("token_a_flag")!=0 or state.get("token_b_flag")!=0:
        raise ValueError("DAMM v2 pool disabled or nonclassic token flags")
    if state.get("liquidity",0)<=0 or state.get("sqrt_price",0)<=0:
        raise ValueError("DAMM v2 missing authenticated liquidity or price")
    if user_input==user_output or user_input in (state["token_a_vault"],state["token_b_vault"]) or user_output in (state["token_a_vault"],state["token_b_vault"]):
        raise ValueError("invalid DAMM v2 user token accounts")
    if referral_token_account is not None:
        raise ValueError("DAMM v2 referral account not authenticated; fail closed")
    program=Pubkey.from_string(PROGRAM)
    event_authority=str(Pubkey.find_program_address([b"__event_authority"],program)[0])
    # Anchor optional referral account is represented by the program ID.
    keys=[
        (POOL_AUTHORITY,False,False),(pool,False,True),
        (user_input,False,True),(user_output,False,True),
        (state["token_a_vault"],False,True),(state["token_b_vault"],False,True),
        (state["token_a_mint"],False,False),(state["token_b_mint"],False,False),
        (payer,True,False),(TOKEN_PROGRAM,False,False),
        (TOKEN_PROGRAM,False,False),(PROGRAM,False,False),
        (event_authority,False,False),(PROGRAM,False,False)]
    metas=[AccountMeta(Pubkey.from_string(a),signer,writable)
           for a,signer,writable in keys]
    data=SWAP2_DISCRIMINATOR+amount_in.to_bytes(8,"little")+min_amount_out.to_bytes(8,"little")+bytes([0])
    return Instruction(program,data,metas)
