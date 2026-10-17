"""Construct and sign a PumpSwap exact-input transaction for local simulation only.

No RPC send call is present. Does not establish real trade profitability.
"""
from arb.pumpswap_local_simulation import local_rpc_only,simulate_signed
from arb.pumpswap_instruction import build_instruction


def sign_and_simulate(rpc, pool, payer, direction, addresses, amount_in, min_out,
                      input_address, output_address, initial_input, initial_output,
                      *, track_volume=None):
    local_rpc_only(rpc)
    if pool.get("verified") is not True or pool.get("canonical_pool_verified") is not True:
        raise ValueError("unverified PumpSwap snapshot")
    if addresses.get("user")!=str(payer.pubkey()) or addresses.get("pool")!=pool.get("address"):
        raise ValueError("payer or pool identity mismatch")
    if direction=="sell":
        mint_in,mint_out=pool["base_mint"],pool["quote_mint"]
        in_key,out_key="user_base_token_account","user_quote_token_account"
    elif direction=="buy_exact_quote_in":
        mint_in,mint_out=pool["quote_mint"],pool["base_mint"]
        in_key,out_key="user_quote_token_account","user_base_token_account"
    else:
        raise ValueError("unsupported PumpSwap direction")
    if addresses.get(in_key)!=input_address or addresses.get(out_key)!=output_address:
        raise ValueError("token account direction mismatch")
    from arb.pumpswap_user_preflight import verify_user_accounts
    verify_user_accounts(rpc,str(payer.pubkey()),input_address,output_address,
                         mint_in,mint_out,initial_input,initial_output)
    ix=build_instruction(direction,addresses,amount_in,min_out,track_volume=track_volume)
    from solders.transaction import Transaction
    from solders.hash import Hash
    from arb.rpc import call
    blockhash=call(rpc,"getLatestBlockhash")["value"]["blockhash"]
    tx=Transaction.new_signed_with_payer(
        [ix],payer.pubkey(),[payer],Hash.from_string(blockhash))
    wire=bytes(tx)
    if len(wire)>1232:
        raise ValueError("PumpSwap transaction exceeds Solana packet limit")
    result=simulate_signed(rpc,wire,input_address,output_address,mint_in,mint_out,
                           initial_input,initial_output,amount_in)
    return {**result,"transaction_bytes":len(wire),"local_only":True,
            "fee_mode_verified":False,"quote_reconciled":False}
