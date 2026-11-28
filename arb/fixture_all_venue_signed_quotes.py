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

def quote_leg(fixture,*,leg_index,amount_in,observed_unix,
              clmm_fee_on_input=True):
    if type(clmm_fee_on_input)is not bool:
        raise ValueError("CLMM source fee mode must be explicit")
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
            from arb.orca_adaptive_fee_source import source_oracle
            orca_fee_oracle=source_oracle(fixture,pool,state)
            lower=sqrt_price_from_tick_index(boundary)
            upper=sqrt_price_from_tick_index(boundary+spacing)
            from arb.whirlpool_ticks import (
                FIXED_LEN,DISC as ORCA_TICK_DISC,DYNAMIC_DISC,
                DYNAMIC_MIN_LEN,DYNAMIC_MAX_LEN,decode_fixed_ticks,
                decode_dynamic_ticks,addresses as orca_array_addresses)
            from arb.orca_multitick_quote import quote_from_decoded_arrays
            from arb.orca_whirlpool import PROGRAM as ORCA_PROGRAM,b58
            import base64
            decoded_arrays=[]
            seen_starts=set()
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
                if len(raw)<12:
                    continue
                is_fixed=len(raw)==FIXED_LEN and raw[:8]==ORCA_TICK_DISC
                is_dynamic=(DYNAMIC_MIN_LEN<=len(raw)<=DYNAMIC_MAX_LEN
                            and raw[:8]==DYNAMIC_DISC)
                if not (is_fixed or is_dynamic):
                    continue
                # A single route can capture arrays belonging to OTHER
                # Whirlpool pools. Only the source-array parent key for this
                # leg is relevant. Never treat unrelated arrays as forged.
                parent=b58(raw[-32:]) if is_fixed else b58(raw[12:44])
                if parent!=pool:
                    continue
                start=int.from_bytes(raw[8:12],"little",signed=True)
                if start in seen_starts:
                    raise ValueError("duplicate Whirlpool tick array start")
                if address!=orca_array_addresses(pool,[start])[0]:
                    raise ValueError("Whirlpool captured tick array PDA mismatch")
                if is_fixed:
                    records=decode_fixed_ticks(raw,pool,start,spacing)
                else:
                    records=decode_dynamic_ticks(raw,pool,start,spacing)
                seen_starts.add(start)
                decoded_arrays.append({"start_tick":start,"ticks":records,
                    "status":"FIXED_VALID" if is_fixed else "DYNAMIC_VALID"})
            sparse=None
            for proof in fixture.get("leg_evidence_by_index",[]):
                if proof.get("pool")==pool and proof.get("auxiliary",{}).get("sparse_tick_source") is not None:
                    from arb.whirlpool_ticks import verify_sparse_tick_fixture,start_tick
                    verify_sparse_tick_fixture(fixture)
                    sparse=proof["auxiliary"]["sparse_tick_source"]
                    if sparse["input_mint"]!=leg["input_mint"]:
                        raise ValueError("Orca sparse source direction mismatch")
                    # Only the observed contiguous prefix is usable. Null
                    # PDAs are not interpreted as liquidity or crossed.
                    first=start_tick(tick,spacing);step=88*spacing*(-1 if sparse["a_to_b"] else 1)
                    by_start={a["start_tick"]:a for a in decoded_arrays}
                    prefix=[]
                    for i in range(3):
                        ix=first+i*step
                        if ix not in by_start or orca_array_addresses(pool,[ix])[0] not in sparse["present_arrays"]:
                            break
                        prefix.append(by_start[ix])
                    decoded_arrays=prefix
            if sparse is not None and not decoded_arrays:
                if orca_fee_oracle is not None:
                    raise ValueError("adaptive Orca sparse current array absent; native quote blocked")
                from arb.orca_spot_quote import quote_inside_observed_absent_array
                native=quote_inside_observed_absent_array(state,leg["input_mint"],amount_in,
                    pool=pool,fixture=fixture)
            elif decoded_arrays:
                if orca_fee_oracle is not None:
                    from arb.orca_adaptive_fee_source import quote_adaptive_from_arrays
                    native=quote_adaptive_from_arrays(
                        state,leg["input_mint"],amount_in,decoded_arrays,
                        orca_fee_oracle,observed_unix=observed_unix)
                else:
                    native=quote_from_decoded_arrays(
                        state,leg["input_mint"],amount_in,
                        decoded_arrays,max_crossings=64)
            else:
                if orca_fee_oracle is not None:
                    raise ValueError("adaptive Whirlpool must have authenticated tick arrays")
                native=quote_bounded_single_tick(state,leg["input_mint"],amount_in,
                    lower_sqrt_x64=lower,upper_sqrt_x64=upper)
            if sparse is not None and "sparse_source_coverage" not in native:
                native["sparse_source_coverage"]={"source_slot":sparse["source_slot"],
                    "present_contiguous_array_starts":[a["start_tick"] for a in decoded_arrays],
                    "observed_absent_arrays":sparse["absent_arrays"],
                    "absent_arrays_crossed":False,"protocol_exact_verified":False}
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
            from arb.raydium_clmm import (
                fee_collected_from_input,fee_collection_source_evidence)
            source_fee_on_input=fee_collected_from_input(
                state,leg["input_mint"])
            # Alternate mode can be requested only as a non-exact scenario.
            selected_fee_on_input=(source_fee_on_input if
                                   clmm_fee_on_input is True else False)
            from arb.raydium_clmm_ticks import POOL_BITMAP_OFFSET,POOL_BITMAP_BYTES
            # extract_pool_states already verifies the manifest, exact pool
            # owner/layout and decoded mint identity. Use its actual raw pool
            # bitmap rather than assuming an absent array is empty.
            pool_raw=base64.b64decode(fixture["accounts"][pool]["data"][0],validate=True)
            bitmap=pool_raw[POOL_BITMAP_OFFSET:POOL_BITMAP_OFFSET+POOL_BITMAP_BYTES]
            extension_raw=None
            for proof in fixture.get("leg_evidence_by_index",[]):
                if proof.get("pool")==pool and proof.get("venue")==v:
                    from arb.raydium_clmm_ticks import verify_extended_direction,extension_bytes
                    extension=verify_extended_direction(pool,leg["input_mint"],proof.get("auxiliary",{}),fixture)
                    if extension is not None:
                        extension_raw=extension_bytes(pool,extension,fixture["accounts"][extension])
            native=quote_across_initialized_ticks(
                {**state,"authenticated_tick_array_starts":array_starts},
                leg["input_mint"],amount_in,fee,candidates,
                max_crossings=32,fee_on_input=selected_fee_on_input,
                default_bitmap_bytes=bitmap,extension_bitmap_bytes=extension_raw)
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
                    if (candidate.get("status")!="DAMM_V2_OFFICIAL_RUST_NATIVE_QUOTE"
                            or candidate.get("pool")!=pool
                            or candidate.get("source_slot")!=row["snapshot_slot"]
                            or candidate.get("input_mint")!=leg["input_mint"]
                            or candidate.get("input_base_units")!=amount_in
                            or type(candidate.get("amount_out")) is not int
                            or candidate["amount_out"]<=0
                            or any(candidate.get(k) is not False for k in SAFE)):
                        raise ValueError("DAMM SDK source result identity mismatch")
                    return {"venue":v,"pool":pool,"leg_index":leg_index,
                        "source_slot":row["snapshot_slot"],
                        "predicted_output_base_units":candidate["amount_out"],
                        "quote_status":"SOURCE_BOUND_INDICATIVE",
                        "native_fee_envelope":candidate,
                        "reason":"official SDK source-clock scenario; execution parity unverified",
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
        native_mode_scenario=(v=="raydium_clmm" and
                              clmm_fee_on_input is False and
                              source_fee_on_input is True)
        return {"venue":v,"pool":pool,"leg_index":leg_index,
                "source_fee_evidence":(fee_collection_source_evidence(
                    state,leg["input_mint"]) if v=="raydium_clmm" else
                    orca_fee_oracle if v=="orca" else None),
                "source_slot":q["snapshot_slot"],
                "predicted_output_base_units":q["amount_out"],
                "quote_status":(
                    "SOURCE_BOUND_FEE_MODE_SCENARIO_NOT_EXACT"
                    if native_mode_scenario else "SOURCE_BOUND_INDICATIVE"),
                "clmm_bitmap_coverage":({"default_pool_bitmap_coverage_used":native["default_pool_bitmap_coverage_used"],
                    "bitmap_proven_empty_array_starts":native["bitmap_proven_empty_array_starts"]}
                    if v=="raydium_clmm" else None),
                "source_fee_mode_scenario":(
                    "OUTPUT_COUNTERFACTUAL" if native_mode_scenario
                    else "SOURCE_POOL_FEE_ON_ENUM"),
                **({"orca_directional_coverage":{
                    k:native[k] for k in ("source","source_array_layout",
                        "directional_boundary_tick","directional_boundary_sqrt_price_x64",
                        "source_current_array_start","source_current_array_initialized_tick_count",
                        "post_sqrt_price_x64","ticks_crossed")
                    }} if v=="orca" and "directional_boundary_tick" in native else {}),
                **({"orca_sparse_source_coverage":native["sparse_source_coverage"]}
                   if v=="orca" and "sparse_source_coverage" in native else {}),
                "protocol_exact_verified":False,**SAFE}
    except (ValueError,KeyError,TypeError,ArithmeticError) as exc:
        return {"venue":v,"pool":pool,"leg_index":leg_index,
                "source_slot":row["snapshot_slot"],
                "predicted_output_base_units":None,"quote_status":"NATIVE_QUOTE_BLOCKED",
                "reason":str(exc)[:240],"protocol_exact_verified":False,**SAFE}
