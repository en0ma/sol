"""Raydium AMM v4 legacy SwapBaseIn instruction constructor.

Account ordering follows Raydium liquidity instruction 9. Construction only:
caller must authenticate pool, OpenBook market and vaults independently.
No RPC writes, swap approvals, or mainnet broadcast.
"""
from arb.token_vaults import TOKEN_PROGRAM

SWAP_BASE_IN_TAG=9

def build_swap(pool,state,amm_authority,market_bids,market_asks,
               market_event_queue,market_base_vault,market_quote_vault,
               market_vault_signer,user_source,user_destination,
               user_owner,amount_in,min_amount_out,*,input_is_base):
    from solders.pubkey import Pubkey
    from solders.instruction import Instruction,AccountMeta
    from arb.venue_watchlist import RECOGNIZED_UNSUPPORTED
    if type(input_is_base)is not bool:
        raise ValueError("Raydium AMM v4 input direction must be explicit")
    if any(type(n)is not int or not 0<n<(1<<64) for n in (amount_in,min_amount_out)):
        raise ValueError("nonzero exact-input amount and threshold required")
    if state.get("status") not in (1,6,7):
        raise ValueError("Raydium AMM v4 pool not enabled")
    if not isinstance(state.get("market_program"),str):
        raise ValueError("missing authenticated market program")
    program=next(k for k,v in RECOGNIZED_UNSUPPORTED.items() if v=="raydium_amm_v4")
    keys=[
        (TOKEN_PROGRAM,False,False),(pool,False,True),
        (amm_authority,False,False),(state["open_orders"],False,True),
        (state["target_orders"],False,True),
        (state["base_vault"],False,True),(state["quote_vault"],False,True),
        (state["market_program"],False,False),(state["market_id"],False,True),
        (market_bids,False,True),(market_asks,False,True),
        (market_event_queue,False,True),(market_base_vault,False,True),
        (market_quote_vault,False,True),(market_vault_signer,False,False),
        (user_source,False,True),(user_destination,False,True),
        (user_owner,True,False)]
    if any(not isinstance(a,str) for a,_,_ in keys):
        raise ValueError("missing Raydium AMM v4 account")
    if user_source==user_destination or user_source in (
            state["base_vault"],state["quote_vault"]) or user_destination in (
            state["base_vault"],state["quote_vault"]):
        raise ValueError("invalid Raydium AMM v4 user token accounts")
    metas=[AccountMeta(Pubkey.from_string(a),signer,writable)
           for a,signer,writable in keys]
    data=bytes([SWAP_BASE_IN_TAG])+amount_in.to_bytes(8,"little")+min_amount_out.to_bytes(8,"little")
    return Instruction(Pubkey.from_string(program),data,metas)
