"""Raydium CLMM swap_v2 instruction builder; not yet fork-execution verified.

Account order and Borsh args from raydium-clmm instructions/swap_v2.rs.
Caller must supply validated ordered tick arrays and funded SPL accounts.
No network submission, quote API, or automatic executable-route admission.
"""
import hashlib
from arb.raydium_clmm import PROGRAM
from arb.token_vaults import TOKEN_PROGRAM
TOKEN_2022="TokenzQdBNbLqP5VEhdkAS6EPF9oM85k2gT8KzWfT5"
MEMO="MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
DISC=hashlib.sha256(b"global:swap_v2").digest()[:8]

def encode(amount,other_amount_threshold,sqrt_price_limit_x64=0,is_base_input=True):
    for name,value,bits in (("amount",amount,64),("threshold",other_amount_threshold,64),
                            ("sqrt limit",sqrt_price_limit_x64,128)):
        if type(value)is not int or not 0<=value<(1<<bits):
            raise ValueError("invalid CLMM "+name)
    if amount==0 or type(is_base_input)is not bool:
        raise ValueError("invalid CLMM amount or mode")
    return (DISC+amount.to_bytes(8,"little")+
            other_amount_threshold.to_bytes(8,"little")+
            sqrt_price_limit_x64.to_bytes(16,"little")+bytes([is_base_input]))

def build(pool,state,payer,user_input,user_output,amount,threshold,tick_arrays,
          input_is_token_0=True,sqrt_price_limit_x64=0,is_base_input=True):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    if type(input_is_token_0)is not bool:raise TypeError("input direction must be bool")
    if not isinstance(tick_arrays,(tuple,list)) or not 1<=len(tick_arrays)<=5:
        raise ValueError("must supply one to five verified tick arrays")
    input_ix=0 if input_is_token_0 else 1
    output_ix=1-input_ix
    mint_input=state[f"token_mint_{input_ix}"]
    mint_output=state[f"token_mint_{output_ix}"]
    vault_input=state[f"token_vault_{input_ix}"]
    vault_output=state[f"token_vault_{output_ix}"]
    keys=[(payer,True,False),(state["amm_config"],False,False),
          (pool,False,True),(user_input,False,True),(user_output,False,True),
          (vault_input,False,True),(vault_output,False,True),
          (state["observation_key"],False,True),
          (TOKEN_PROGRAM,False,False),(TOKEN_2022,False,False),
          (MEMO,False,False),(mint_input,False,False),(mint_output,False,False)]
    keys.extend((a,False,True) for a in tick_arrays)
    if len({str(a) for a,_,_ in keys[13:]})!=len(tick_arrays):
        raise ValueError("duplicate tick arrays")
    metas=[AccountMeta(Pubkey.from_string(key),signer,writable)
           for key,signer,writable in keys]
    return Instruction(Pubkey.from_string(PROGRAM),
                       encode(amount,threshold,sqrt_price_limit_x64,is_base_input),metas)
