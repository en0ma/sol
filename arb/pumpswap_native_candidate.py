"""PumpSwap V2 exact-input *candidate* quote from the October 2026 SDK math.

No fee defaults. Requires authenticated pool snapshot; does not authorize a
trade until SDK cross-check and four real signed swap parity trials succeed.
Reference: @pump-fun/pump-swap-sdk 2.1.0 src/sdk/{buy,sell,fees,util}.ts.
"""
ZERO="11111111111111111111111111111111"
SOL="So11111111111111111111111111111111111111112"
USDC="EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
BPS=10_000
MAYHEM_SUPPLY=1_000_000_000_000_000


def fee(amount,bps):
    if type(amount) is not int or amount<0 or type(bps) is not int or not 0<=bps<BPS:
        raise ValueError("invalid fee amount or rate")
    return (amount*bps+BPS-1)//BPS


def select_rates(pool):
    """Require verified on-chain FeeConfig and unambiguous quote mint class."""
    if not isinstance(pool,dict) or pool.get("verified") is not True or (
            pool.get("canonical_pool_verified") is not True):
        raise ValueError("authenticated PumpSwap canonical identity required")
    config=pool.get("fee_config")
    if not isinstance(config,dict) or config.get("account_authenticated") is not True:
        raise ValueError("authenticated PumpSwap FeeConfig required")
    if pool.get("creator_fee_bps",0):
        # Existing GlobalConfig decoder does not expose creatorFeeConfigurable.
        raise ValueError("per-pool creator fee gate not authenticated")
    if pool.get("is_cashback_coin") not in (0,1):
        raise ValueError("cashback status not authenticated")
    if pool["is_cashback_coin"]:
        raise ValueError("cashback pool does not support PumpSwap V2 swaps")
    if pool.get("is_mayhem_mode") not in (0,1):
        raise ValueError("Mayhem fee classification unverified")
    if pool.get("canonical") is not True:
        rates=config.get("flat_fees")
    else:
        quote=pool.get("quote_mint")
        if quote in (SOL,ZERO):
            tier=config.get("fee_tiers")
        elif quote==USDC:
            tier=config.get("stable_fee_tiers") or config.get("fee_tiers")
        else:
            exotic=config.get("exotic_flat_fees")
            rates=(exotic if isinstance(exotic,dict) and any(exotic.values())
                   else config.get("flat_fees"))
            tier=None
        if quote in (SOL,ZERO,USDC):
            if not isinstance(tier,list) or not tier:
                raise ValueError("missing PumpSwap quote-mint fee tiers")
            base=pool.get("base_reserve")
            priced=pool.get("quote_vault_balance",0)+pool.get("virtual_quote_reserves",0)
            supply=(MAYHEM_SUPPLY if pool["is_mayhem_mode"] else pool.get("base_mint_supply"))
            if any(type(x) is not int or x<=0 for x in (base,priced,supply)):
                raise ValueError("missing fee tier market cap reserves/supply")
            market_cap=priced*supply//base
            rates=tier[0]["fees"]
            for row in tier:
                if market_cap>=row["market_cap_threshold"]:
                    rates=row["fees"]
    keys=("lp_fee_bps","protocol_fee_bps","creator_fee_bps")
    if not isinstance(rates,dict) or any(type(rates.get(k)) is not int or
                                        not 0<=rates[k]<BPS for k in keys):
        raise ValueError("invalid on-chain PumpSwap fee rates")
    if sum(rates[k] for k in keys)>=BPS:
        raise ValueError("excessive PumpSwap fee rates")
    if not isinstance(pool.get("coin_creator"),str):
        raise ValueError("authenticated coin creator identity required")
    if pool["coin_creator"]==ZERO:
        rates={**rates,"creator_fee_bps":0}
    return rates


def quote_exact_input(pool,mint_in,amount_in):
    if type(amount_in) is not int or not 0<amount_in<2**64:
        raise ValueError("invalid exact-input amount")
    rates=select_rates(pool)
    base=pool.get("base_reserve")
    physical=pool.get("quote_vault_balance")
    virtual=pool.get("virtual_quote_reserves")
    protocol=pool.get("protocol_fees_accrued")
    creator=pool.get("creator_fees_accrued")
    if any(type(x) is not int for x in (base,physical,virtual,protocol,creator)):
        raise ValueError("missing PumpSwap V2 reserves or accrued fee buckets")
    effective=physical+virtual
    spendable=physical-protocol-creator
    if base<=0 or effective<=0 or spendable<=0 or protocol<0 or creator<0:
        raise ValueError("invalid PumpSwap physical or virtual reserves")
    if mint_in==pool.get("quote_mint"):
        if pool.get("global_config",{}).get("buy_enabled") is not True:
            raise ValueError("PumpSwap buy disabled")
        total=sum(rates.values())
        net=amount_in*BPS//(BPS+total)
        if net<=0:raise ValueError("quote cannot cover fees")
        charge=sum(fee(net,r) for r in rates.values())
        excess=max(0,net+charge-amount_in)
        net-=excess
        if net<=1:raise ValueError("quote too small for exact-input buy")
        # SDK buyQuoteInput subtracts one before pool swap division.
        internal=net-1
        out=base*internal//(effective+internal)
        direction="buy_exact_quote_in"
        mint_out=pool["base_mint"]
    elif mint_in==pool.get("base_mint"):
        if pool.get("global_config",{}).get("sell_enabled") is not True:
            raise ValueError("PumpSwap sell disabled")
        gross=effective*amount_in//(base+amount_in)
        charges={k:fee(gross,v) for k,v in rates.items()}
        if gross-charges["lp_fee_bps"]>spendable:
            raise ValueError("sell gross outflow exceeds real available reserves")
        out=gross-sum(charges.values())
        direction="sell"
        mint_out=pool["quote_mint"]
    else:
        raise ValueError("mint not in PumpSwap pool")
    if out<=0 or out>=2**64:
        raise ValueError("PumpSwap dust or invalid native quote")
    return {"venue":"pumpswap","direction":direction,"mint_in":mint_in,
            "mint_out":mint_out,"amount_in":amount_in,
            "native_formula_candidate_out":out,"fee_rates_bps":rates,
            "status":"UNVERIFIED_NATIVE_FORMULA_CANDIDATE",
            "official_sdk_parity_verified":False,"signed_parity_verified":False,
            "actionable":False,"broadcast":False}
