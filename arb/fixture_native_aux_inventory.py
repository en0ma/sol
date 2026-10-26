"""Decode captured auxiliary pricing accounts for all four incomplete venues.

Owner, manifest membership and program-specific discriminator are checked on
the actual bytes. Decoded partial state is not silently promoted to a fee.
"""
import base64
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.source_snapshot_manifest import verify
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def inspect(fixture,*,pool_filter=None):
    verify(fixture)
    rows=extract_pool_states(fixture)
    result=[]
    for row in rows:
        if pool_filter is not None and row["address"]!=pool_filter:
            continue
        venue=row["venue"]
        if venue not in ("raydium_clmm","meteora_dlmm","meteora_damm_v2","pumpswap"):continue
        pool=row["decoded_pool_state"]
        accounts=fixture["accounts"]
        included=set(fixture["state_account_addresses"])
        record={"venue":venue,"pool":row["address"],"source_slot":row["snapshot_slot"],
                "decoded_auxiliary":[],"missing":[]}
        if venue=="raydium_clmm":
            from arb.fixture_aux_fee_decoder import decode_native_config_fee
            config=decode_native_config_fee(venue,pool,fixture)
            record["decoded_auxiliary"].append({"type":"amm_config",
                 "account":config["config_address"],
                 "trade_fee_ppm":config["trade_fee_ppm"]})
            from arb.raydium_clmm_ticks import SIZE,DISC
            from arb.orca_whirlpool import b58
            for address in fixture["state_account_addresses"]:
                info=accounts[address]
                if info.get("owner")!="CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK":
                    continue
                data=info.get("data")
                if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":continue
                raw=base64.b64decode(data[0],validate=True)
                if len(raw)==SIZE and raw[:8]==DISC and b58(raw[8:40])==row["address"]:
                    record["decoded_auxiliary"].append({"type":"tick_array","account":address,
                        "start_tick":int.from_bytes(raw[40:44],"little",signed=True)})
            if not any(a["type"]=="tick_array" for a in record["decoded_auxiliary"]):
                record["missing"].append("initialized_tick_array")
        elif venue=="meteora_dlmm":
            from arb.meteora_dlmm_bin_preflight import BIN_ARRAY_DISC,BIN_ARRAY_SIZE
            from arb.meteora_dlmm import PROGRAM
            from arb.orca_whirlpool import b58
            for address in fixture["state_account_addresses"]:
                info=accounts[address]
                if info.get("owner")!=PROGRAM:continue
                data=info.get("data")
                if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":continue
                raw=base64.b64decode(data[0],validate=True)
                if len(raw)>=56 and raw[:8]==BIN_ARRAY_DISC and b58(raw[24:56])==row["address"]:
                    record["decoded_auxiliary"].append({"type":"bin_array","account":address,
                        "array_index":int.from_bytes(raw[8:16],"little",signed=True),
                        "array_size":BIN_ARRAY_SIZE})
            if not any(a["type"]=="bin_array" for a in record["decoded_auxiliary"]):
                record["missing"].append("active_bin_array")
            record["missing"].append("decoded_dynamic_fee_parameters")
        elif venue=="meteora_damm_v2":
            record["decoded_auxiliary"].append({"type":"pool_liquidity",
                "sqrt_price_x64":pool["sqrt_price"],"liquidity":pool["liquidity"]})
            record["missing"].append("decoded_dynamic_fee_scheduler_and_curve_config")
        else:
            from arb.fixture_pool_fundamentals import extract as native_fundamentals
            fundamentals=next((x for x in native_fundamentals(fixture)["fundamentals"]
                if x["venue"]=="pumpswap" and x["address"]==row["address"]),None)
            if fundamentals is None:
                raise ValueError("PumpSwap source SPL vault state unavailable")
            base,quote=fundamentals["vault_base_units"]
            protocol=pool.get("protocol_fees")
            creator=pool.get("creator_fees")
            virtual=pool.get("virtual_quote_reserves")
            if all(type(n)is int for n in (base,quote,protocol,creator,virtual)):
                spendable=quote-protocol-creator
                priced=quote+virtual
                if base<=0 or quote<=0 or spendable<=0 or priced<=0:
                    raise ValueError("PumpSwap accrued fee buckets exhaust liquidity")
                record["decoded_auxiliary"].append({"type":"pool_net_quote_liquidity",
                    "base_vault_base_units":base,"quote_vault_base_units":quote,
                    "protocol_fee_liability_base_units":protocol,
                    "creator_fee_liability_base_units":creator,
                    "virtual_quote_reserves_base_units":virtual,
                    "spendable_quote_base_units":spendable,
                    "priced_quote_base_units":priced})
            else:
                record["missing"].append("pool_accrued_fee_bucket_fields")
            # Pump fee rates cannot be treated as effective without PDA
            # derivation, market-cap selection and fee-mode authentication.
            from arb.pumpswap_fee_config import DISC,decode
            from arb.pumpswap_fee_account import PROGRAM
            for address in fixture["state_account_addresses"]:
                info=accounts[address]
                if info.get("owner")!=PROGRAM:continue
                data=info.get("data")
                if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":continue
                raw=base64.b64decode(data[0],validate=True)
                if raw[:8]==DISC:
                    decoded=decode(raw)
                    record["decoded_auxiliary"].append({"type":"pump_fee_config",
                        "account":address,"flat_fee_bps":decoded["flat_fees"],
                        "standard_tiers":len(decoded["fee_tiers"]),
                        "stable_tiers":len(decoded["stable_fee_tiers"])})
            if not any(a["type"]=="pump_fee_config" for a in record["decoded_auxiliary"]):
                record["missing"].append("pump_fee_config")
            record["missing"].append("pda_and_dynamic_tier_verified")
        record.update(fully_priced=False,**SAFE)
        result.append(record)
    return {"source_slot":fixture["state_accounts_observed_slot"],
            "venues":result,"full_native_fee_pricing_verified":False,**SAFE}

def inspect_isolated(fixture):
    """Decode source auxiliary evidence independently for each venue pool.

    One malformed fee account cannot suppress other venue evidence; all
    accounting and manifest validation continues to run for each pool.
    """
    verify(fixture)
    rows=extract_pool_states(fixture)
    output=[]
    for row in rows:
        venue=row["venue"]
        if venue not in ("raydium_clmm","meteora_dlmm","meteora_damm_v2","pumpswap"):
            continue
        try:
            evidence=inspect(fixture,pool_filter=row["address"])["venues"]
            if len(evidence)!=1:
                raise ValueError("native venue account decode incomplete")
            output.append(evidence[0])
        except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
            output.append({"venue":venue,"pool":row["address"],
                "source_slot":row["snapshot_slot"],
                "status":"AUXILIARY_DECODE_BLOCKED","reason":str(exc)[:240],
                "decoded_auxiliary":[],"missing":["native_auxiliary_decoder_blocked"],
                "fully_priced":False,**SAFE})
    return {"source_slot":fixture["state_accounts_observed_slot"],
            "venues":output,"full_native_fee_pricing_verified":False,**SAFE}
