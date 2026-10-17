"""PumpSwap ordered account-meta specification, directly from pump_amm IDL.

Requires externally PDA-verified addresses. Returns descriptions only;
does not sign, submit or claim executable trade readiness.
"""
SELL=["pool","user","global_config","base_mint","quote_mint","user_base_token_account","user_quote_token_account","pool_base_token_account","pool_quote_token_account","protocol_fee_recipient","protocol_fee_recipient_token_account","base_token_program","quote_token_program","system_program","associated_token_program","event_authority","program","coin_creator_vault_ata","coin_creator_vault_authority","fee_config","fee_program"]
BUY_EXACT_QUOTE_IN=["pool","user","global_config","base_mint","quote_mint","user_base_token_account","user_quote_token_account","pool_base_token_account","pool_quote_token_account","protocol_fee_recipient","protocol_fee_recipient_token_account","base_token_program","quote_token_program","system_program","associated_token_program","event_authority","program","coin_creator_vault_ata","coin_creator_vault_authority","global_volume_accumulator","user_volume_accumulator","fee_config","fee_program"]
WRITABLE=set(("pool","user","user_base_token_account","user_quote_token_account",
              "pool_base_token_account","pool_quote_token_account",
              "protocol_fee_recipient_token_account","coin_creator_vault_ata",
              "user_volume_accumulator"))
SIGNERS={"user"}


def account_metas(direction, addresses):
    if direction not in ("sell","buy_exact_quote_in"):
        raise ValueError("unsupported PumpSwap exact-input instruction")
    names=SELL if direction=="sell" else BUY_EXACT_QUOTE_IN
    if not isinstance(addresses,dict):
        raise ValueError("missing account address map")
    result=[]
    for name in names:
        address=addresses.get(name)
        if not isinstance(address,str) or not address.strip():
            raise ValueError("missing PumpSwap account: "+name)
        result.append({"name":name,"address":address,"is_writable":name in WRITABLE,
                       "is_signer":name in SIGNERS})
    if addresses["program"]!="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA" or addresses["fee_program"]!="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ":
        raise ValueError("PumpSwap or fee program mismatch")
    if len({x["address"] for x in result})!=len(result):
        raise ValueError("duplicate PumpSwap account addresses")
    return {"direction":direction,"metas":result,"fully_verified":False,
            "transaction_built":False,"simulation_verified":False}
