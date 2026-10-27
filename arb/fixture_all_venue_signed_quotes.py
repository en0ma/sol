"""Direct manifest-bound, venue-native quote attempt for all seven signed legs.

Never inject synthetic liquidity/fees. Every venue uses its own native state
decoder or returns an explicit missing-auxiliary-state blocker. No coordinator
logic and no broadcast.
"""
from arb.fixture_quote_execution_pipeline import extract_pool_states
from arb.fixture_config_quote_projection import quote_cpmm_creator_fee_source
from arb.raydium_amm_v4_fixture_quote import quote_from_fixture
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
VENUES=frozenset(("orca","raydium_cpmm","raydium_clmm","meteora_dlmm",
                  "meteora_damm_v2","pumpswap","raydium_amm_v4"))

def quote_leg(fixture,*,leg_index,amount_in,observed_unix):
    if type(leg_index)is not int or not 0<=leg_index<6 or type(amount_in)is not int or not 0<amount_in<2**64:
        raise ValueError("invalid signed leg number or amount")
    rows=extract_pool_states(fixture)
    if not 2<=len(rows)<=6 or leg_index>=len(rows):
        raise ValueError("two to six source-bound decoded pool states required")
    row=rows[leg_index]
    v=row["venue"]
    m=fixture["route_mints"]
    pool=row["address"]
    if v not in VENUES or {m[leg_index],m[leg_index+1]}!=set(row["mints"]):
        raise ValueError("source leg direction or venue mismatch")
    leg={"venue":v,"pool":pool,"input_mint":m[leg_index],
         "output_mint":m[leg_index+1]}
    try:
        if v=="raydium_cpmm":
            result=quote_cpmm_creator_fee_source(fixture,observed_unix=observed_unix,
                 leg=leg,amount_in=amount_in)
            q=result["quote"]
        elif v=="raydium_amm_v4":
            result=quote_from_fixture(fixture,pool=pool,input_mint=leg["input_mint"],
                amount_in=amount_in,observed_unix=observed_unix)
            q=result["quote"]
        elif v=="orca":
            # A Whirlpool source pool provides liquidity, fee and current tick;
            # boundary prices are derived via the venue's exact integer tick math.
            from arb.orca_tick_math import sqrt_price_from_tick_index
            from arb.orca_spot_quote import quote_bounded_single_tick
            state=row["decoded_pool_state"]
            spacing=state["tick_spacing"]
            tick=state["tick_current_index"]
            boundary=(tick//spacing)*spacing
            if spacing<=0 or not -443636<=boundary<boundary+spacing<=443636:
                raise ValueError("Whirlpool tick span outside native protocol bounds")
            lower=sqrt_price_from_tick_index(boundary)
            upper=sqrt_price_from_tick_index(boundary+spacing)
            native=quote_bounded_single_tick(state,leg["input_mint"],amount_in,
                lower_sqrt_x64=lower,upper_sqrt_x64=upper)
            q={**leg,"amount_in":amount_in,
               "amount_out":native["estimated_output_base_units"],
               "snapshot_slot":row["snapshot_slot"]}
        elif v=="raydium_clmm":
            from arb.fixture_aux_fee_decoder import decode_native_config_fee
            from arb.raydium_clmm_tick_decode import initialized_ticks,next_boundary
            from arb.raydium_clmm_within_tick_quote import quote_within_tick
            from arb.orca_tick_math import sqrt_price_from_tick_index
            import base64
            from arb.raydium_clmm_ticks import SIZE,DISC
            state=row["decoded_pool_state"]
            fee=decode_native_config_fee(v,state,fixture)["trade_fee_ppm"]
            downward=leg["input_mint"]==state["token_mint_0"]
            candidates=[]
            for address in fixture["state_account_addresses"]:
                account=fixture["accounts"].get(address,{})
                if account.get("owner")!="CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK" or account.get("executable") is not False:
                    continue
                data=account.get("data")
                if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":continue
                raw=base64.b64decode(data[0],validate=True)
                if len(raw)!=SIZE or raw[:8]!=DISC:continue
                from arb.orca_whirlpool import b58
                if b58(raw[8:40])!=pool:continue
                start=int.from_bytes(raw[40:44],"little",signed=True)
                from arb.raydium_clmm_ticks import tick_array_pda,start_tick
                if address!=tick_array_pda(pool,start):
                    raise ValueError("CLMM captured tick array has noncanonical PDA")
                if start%(60*state["tick_spacing"])!=0:
                    raise ValueError("CLMM source tick array start is misaligned")
                candidates.extend(initialized_ticks(raw,start,state["tick_spacing"]))
            if not candidates:
                raise ValueError("CLMM initialized source ticks unavailable")
            index=next_boundary(candidates,state["tick_current"],downward)
            native=quote_within_tick(state,leg["input_mint"],amount_in,fee,
                sqrt_price_from_tick_index(index))
            q={**leg,"amount_in":amount_in,
               "amount_out":native["estimated_output_base_units"],
               "snapshot_slot":row["snapshot_slot"]}
        elif v in ("meteora_dlmm","meteora_damm_v2","pumpswap"):
            from arb.m5_complex_venue_native_quote import quote_auxiliary
            # Decoders must attach explicit account-derived state, not just
            # fee numbers from an untrusted API. None is intentionally blocked.
            native_aux=fixture.get("source_native_auxiliary_quotes",{})
            auxiliary=native_aux.get(pool) if isinstance(native_aux,dict) else None
            if auxiliary is None:
                if v=="meteora_dlmm":
                    from arb.meteora_dlmm_source_fee_envelope import quote_fee_envelope
                    bound=quote_fee_envelope(fixture,pool=pool,
                        mint_in=leg["input_mint"],amount_in=amount_in,
                        observed_unix=observed_unix)
                    return {"venue":v,"pool":pool,"leg_index":leg_index,
                        "source_slot":row["snapshot_slot"],
                        "predicted_output_base_units":None,
                        "quote_status":"NATIVE_QUOTE_BOUNDED_NOT_EXACT"
                             if "lower_output_bound" in bound else "NATIVE_QUOTE_BLOCKED",
                        "native_fee_envelope":bound,
                        "reason":"effective DLMM dynamic fee and execution parity unverified",
                        "protocol_exact_verified":False,**SAFE}
                if v=="pumpswap":
                    from arb.pumpswap_source_fee_envelope import quote_fee_candidates
                    candidate=quote_fee_candidates(fixture,pool=pool,
                        mint_in=leg["input_mint"],amount_in=amount_in)
                    return {"venue":v,"pool":pool,"leg_index":leg_index,
                        "source_slot":row["snapshot_slot"],
                        "predicted_output_base_units":None,
                        "quote_status":"NATIVE_QUOTE_BOUNDED_NOT_EXACT"
                            if "lower_output_bound" in candidate else "NATIVE_QUOTE_BLOCKED",
                        "native_fee_envelope":candidate,
                        "reason":"effective PumpSwap market-cap tier and mode unverified",
                        "protocol_exact_verified":False,**SAFE}
                if v=="meteora_damm_v2":
                    from arb.meteora_damm_v2_source_scenarios import scenario_envelope
                    candidate=scenario_envelope(fixture,pool=pool,
                        mint_in=leg["input_mint"],amount_in=amount_in)
                    return {"venue":v,"pool":pool,"leg_index":leg_index,
                        "source_slot":row["snapshot_slot"],
                        "predicted_output_base_units":None,
                        "quote_status":"NATIVE_QUOTE_BOUNDED_NOT_EXACT",
                        "native_fee_envelope":candidate,
                        "reason":"DAMM v2 fee scheduler and curve model unverified",
                        "protocol_exact_verified":False,**SAFE}
                raise ValueError("MISSING_NATIVE_AUXILIARY_STATE: "+v+
                    " source-verified effective fees, reserves and/or bin arrays")
            q=quote_auxiliary(fixture,row,venue=v,
                mint_in=leg["input_mint"],amount_in=amount_in,auxiliary=auxiliary)
        else:
            raise ValueError("unsupported source venue")
        if (q.get("pool")!=pool or q.get("venue")!=v or
            q.get("input_mint")!=m[leg_index] or
            q.get("output_mint")!=m[leg_index+1] or
            q.get("amount_in")!=amount_in or
            q.get("snapshot_slot")!=fixture["state_accounts_observed_slot"] or
            type(q.get("amount_out"))is not int or q["amount_out"]<=0):
            raise ValueError("native quote does not match signed source identity")
        return {"venue":v,"pool":pool,"leg_index":leg_index,
                "source_slot":q["snapshot_slot"],
                "predicted_output_base_units":q["amount_out"],
                "quote_status":"SOURCE_BOUND_INDICATIVE",
                "protocol_exact_verified":False,**SAFE}
    except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
        return {"venue":v,"pool":pool,"leg_index":leg_index,
                "source_slot":row["snapshot_slot"],
                "predicted_output_base_units":None,"quote_status":"NATIVE_QUOTE_BLOCKED",
                "reason":str(exc)[:240],"protocol_exact_verified":False,**SAFE}
