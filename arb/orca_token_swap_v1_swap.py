"""Legacy SPL Token Swap v1 exact-input instruction construction only.

Does not approve execution or bypass on-chain pool/vault authentication.
"""
from arb.token_vaults import TOKEN_PROGRAM

SWAP_TAG=1

def build_swap(program,pool,pool_authority,transfer_authority,
               user_source,pool_source,pool_destination,user_destination,
               pool_mint,pool_fee_account,amount_in,min_amount_out):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    if any(type(x)is not int or not 0<x<(1<<64) for x in (amount_in,min_amount_out)):
        raise ValueError("nonzero u64 input and output threshold required")
    addresses=(program,pool,pool_authority,transfer_authority,user_source,
               pool_source,pool_destination,user_destination,pool_mint,pool_fee_account)
    if any(not isinstance(x,str) for x in addresses):
        raise ValueError("missing swap account")
    if len({user_source,pool_source,pool_destination,user_destination})!=4:
        raise ValueError("source and destination token accounts must be distinct")
    keys=[
        (pool,False,False),(pool_authority,False,False),
        (transfer_authority,True,False),(user_source,False,True),
        (pool_source,False,True),(pool_destination,False,True),
        (user_destination,False,True),(pool_mint,False,True),
        (pool_fee_account,False,True),(TOKEN_PROGRAM,False,False)]
    metas=[AccountMeta(Pubkey.from_string(a),signer,writable)
           for a,signer,writable in keys]
    data=bytes([SWAP_TAG])+amount_in.to_bytes(8,"little")+min_amount_out.to_bytes(8,"little")
    return Instruction(Pubkey.from_string(program),data,metas)
