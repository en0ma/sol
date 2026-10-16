"""Resolve PumpSwap invariant accounts and PDAs for exact-input instructions.

Derived addresses follow the official pump_amm instruction IDL. This supplies
account addresses but does not verify fee recipient selection, mint accounts
or transaction success. Never broadcast.
"""
from arb.pumpswap_pool import PROGRAM
from arb.pumpswap_fee_account import PROGRAM as FEE_PROGRAM, authenticated_address
from arb.pumpswap_global_config import ADDRESS as GLOBAL_CONFIG
from arb.token_vaults import TOKEN_PROGRAM

SYSTEM="11111111111111111111111111111111"
ATA="ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"


def resolve(pool, user, user_base, user_quote, protocol_fee_recipient, *,
            quote_token_program=TOKEN_PROGRAM):
    if not isinstance(pool,dict) or pool.get("verified") is not True:
        raise ValueError("verified pool snapshot required")
    if pool.get("canonical_pool_verified") is not True:
        raise ValueError("verified pool creator required")
    if quote_token_program!=TOKEN_PROGRAM:
        raise ValueError("only classic SPL quote tokens supported")
    from solders.pubkey import Pubkey
    def pk(value):
        if not isinstance(value,str):raise ValueError("invalid account address")
        return Pubkey.from_string(value)
    program=pk(PROGRAM)
    base_mint=pk(pool["base_mint"])
    quote_mint=pk(pool["quote_mint"])
    recipient=pk(protocol_fee_recipient)
    def pda(seeds,owner=program):
        return str(Pubkey.find_program_address(seeds,owner)[0])
    def ata(owner,mint):
        return pda([bytes(pk(owner)),bytes(pk(TOKEN_PROGRAM)),bytes(pk(mint))],pk(ATA))
    fee_address,_=authenticated_address()
    creator=pool.get("coin_creator")
    if not isinstance(creator,str):
        raise ValueError("missing verified coin creator")
    creator_authority=pda([b"creator_vault",bytes(pk(creator))])
    return {
        "pool":pool["address"],"user":user,"global_config":GLOBAL_CONFIG,
        "base_mint":pool["base_mint"],"quote_mint":pool["quote_mint"],
        "user_base_token_account":user_base,"user_quote_token_account":user_quote,
        "pool_base_token_account":pool["base_vault"],
        "pool_quote_token_account":pool["quote_vault"],
        "protocol_fee_recipient":protocol_fee_recipient,
        "protocol_fee_recipient_token_account":ata(protocol_fee_recipient,pool["quote_mint"]),
        "base_token_program":TOKEN_PROGRAM,"quote_token_program":quote_token_program,
        "system_program":SYSTEM,"associated_token_program":ATA,
        "event_authority":pda([b"__event_authority"]),
        "program":PROGRAM,
        "coin_creator_vault_ata":ata(creator_authority,pool["quote_mint"]),
        "coin_creator_vault_authority":creator_authority,
        "global_volume_accumulator":pda([b"global_volume_accumulator"]),
        "user_volume_accumulator":pda([b"user_volume_accumulator",bytes(pk(user))]),
        "fee_config":fee_address,"fee_program":FEE_PROGRAM}
