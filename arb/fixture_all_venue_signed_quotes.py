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
            from arb.whirlpool_ticks import (
                FIXED_LEN,DISC as ORCA_TICK_DISC,decode_fixed_ticks,
                addresses as orca_array_addresses)
            from arb.orca_multitick_quote import quote_from_decoded_arrays
            from arb.orca_whirlpool import PROGRAM as ORCA_PROGRAM
            import base64
            decoded_arrays=[]
            for address in fixture["state_account_addresses"]:
                account=fixture["accounts"].get(address)
                if not isinstance(account,dict) or account.get("owner")!=ORCA_PROGRAM:
                    continue
                if account.get("executable") is not False:
                    raise ValueError("executable Whirlpool pool tick state rejected")
                data=account.get("data")
                if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
                    raise ValueError("unauthenticated Whirlpool source array encoding")
                raw=base64.b64decode(data[0],validate=True)
                if len(raw)!=FIXED_LEN or raw[:8]!=ORCA_TICK_DISC:
                    continue
                start=int.from_bytes(raw[8:12],"little",signed=True)
                if address!=orca_array_addresses(pool,[start])[0]:
                    raise ValueError("Whirlpool captured tick array PDA mismatch")
                records=decode_fixed_ticks(raw,pool,start,spacing)
                decoded_arrays.append({"start_tick":start,"ticks":records,
                                       "status":"FIXED_VALID"})
            if decoded_arrays:
                # Reuse the existing exact-input Orca venue model, rather than
                # pretending the current tick has infinite constant liquidity.
                native=quote_from_decoded_arrays(state,leg["input_mint"],amount_in,
                    decoded_arrays,max_crossings=12)
            else:
                native=quote_bounded_single_tick(state,leg["input_mint"],amount_in,
                    lower_sqrt_x64=lower,upper_sqrt_x64=upper)
            q={**leg,"amount_in":amount_in,
               "amount_out":native["estimated_output_base_units"],
               "snapshot_slot":row["snapshot_slot"]}
        elif v=="raydium_clmm":
            from arb.fixture_aux_fee_decoder import decode_native_config_fee
            from arb.raydium_clmm_tick_decode import initialized_ticks
            from arb.raydium_clmm_cross_tick_quote import quote_across_initialized_ticks
            import base64
            from arb.raydium_clmm_ticks import SIZE,DISC
            state=row["decoded_pool_state"]
            fee=decode_native_config_fee(v,state,fixture)["trade_fee_ppm"]
            downward=leg["input_mint"]==state["token_mint_0"]
            candidates=[]
            array_starts=[]
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
                array_starts.append(start)
                candidates.extend(initialized_ticks(raw,start,state["tick_spacing"]))
            if not candidates:
                raise ValueError("CLMM initialized source ticks unavailable")
            native=quote_across_initialized_ticks(
                {**state,"authenticated_tick_array_starts":array_starts},
                leg["input_mint"],amount_in,fee,candidates,
                max_crossings=32)
            q={**leg,"amount_in":amount_in,
               "amount_out":native["amount_out"],
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
                        "quote_status":("NATIVE_QUOTE_SOURCE_DERIVED_NOT_EXACT"
                            if isinstance(bound.get("source_derived_dynamic_fee_quote"),dict)
                            and type(bound["source_derived_dynamic_fee_quote"].get("amount_out")) is int
                            else "NATIVE_QUOTE_BOUNDED_NOT_EXACT"
                            if "lower_output_bound" in bound else "NATIVE_QUOTE_BLOCKED"),
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
                        "quote_status":("NATIVE_QUOTE_SELECTED_FEE_MODE_NOT_EXACT"
                            if candidate.get("fee_mode_selected_from_source") is True
                            and len(candidate.get("candidates",[]))==1
                            else "NATIVE_QUOTE_MODELED_NOT_EXACT"
                            if "minimum_candidate_output" in candidate else "NATIVE_QUOTE_BLOCKED"),
                        "native_fee_envelope":candidate,
                        "reason":"effective PumpSwap market-cap tier and mode unverified",
                        "protocol_exact_verified":False,**SAFE}
                if v=="meteora_damm_v2":
                    from arb.meteora_damm_v2_source_scenarios import scenario_envelope
                    candidate=scenario_envelope(fixture,pool=pool,
                        mint_in=leg["input_mint"],amount_in=amount_in,
                        observed_unix=observed_unix)
                    return {"venue":v,"pool":pool,"leg_index":leg_index,
                        "source_slot":row["snapshot_slot"],
                        "predicted_output_base_units":None,
                        "quote_status":("NATIVE_QUOTE_SOURCE_BASE_FEE_NOT_EXACT"
                            if isinstance(candidate.get("source_pool_fee_schedule"),dict)
                            and candidate["source_pool_fee_schedule"].get("status")==
                                "SOURCE_DAMM_BASE_FEE_ONLY_NOT_PROTOCOL_EXACT"
                            and candidate["source_pool_fee_schedule"].get("dynamic_fee_initialized") is False
                            else "NATIVE_QUOTE_MODELED_NOT_EXACT"),
                        "native_fee_envelope":candidate,
                        "reason":"DAMM v2 effective dynamic fee or curve parity unverified",
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
