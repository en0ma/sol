"""Fail-closed atomic instruction assembly for four verified swap-builder venues.

Assembly only: independently verified account states, SPL user accounts,
per-hop exact-input amounts, oracles and onchain quotes remain caller duties.
Never broadcasts or authorizes live trading.
"""
from arb.orca_whirlpool import SOL, USDC
from arb.whirlpool_swap import build_swap
from arb.raydium_swap import instruction as build_cpmm
from arb.token_vaults import TOKEN_PROGRAM
from arb.meteora_dlmm_swap import build_swap as build_dlmm
from arb.raydium_clmm_swap import build as build_clmm

MAX_HOPS=3

def assemble_mixed_cycle(route, pool_states, oracles, user_accounts,
                         authority, amounts, min_outputs):
    legs=route.get("legs",[])
    tokens=route.get("tokens",[])
    if not 2<=len(legs)<=MAX_HOPS or len(tokens)!=len(legs)+1:
        raise ValueError("two or three connected swap legs required")
    if tokens[0] not in (SOL,USDC) or tokens[-1]!=tokens[0]:
        raise ValueError("route must close in exact WSOL or USDC starting mint")
    if len(set((leg["venue"],leg["pool"]) for leg in legs))!=len(legs):
        raise ValueError("pool reuse disabled")
    if len(amounts)!=len(legs) or len(min_outputs)!=len(legs):
        raise ValueError("per-hop quantities required")
    if not isinstance(authority,str) or not authority or any(t not in user_accounts for t in tokens):
        raise ValueError("missing authority or user token account")
    instructions=[]
    for i,leg in enumerate(legs):
        source,target=tokens[i:i+2]
        if (leg.get("from"),leg.get("to"))!=(source,target):
            raise ValueError("graph leg disconnected")
        amount,threshold=amounts[i],min_outputs[i]
        if any(type(x) is not int or not 0<x<1<<64 for x in (amount,threshold)):
            raise ValueError("invalid per-hop exact-input amount or nonzero minimum")
        state=pool_states[leg["pool"]]
        venue=leg.get("venue")
        if venue=="orca":
            a,b=state["token_mint_a"],state["token_mint_b"]
            if (source,target)!=(a,b) and (source,target)!=(b,a):
                raise ValueError("Orca onchain pool mints disagree")
            instructions.append(build_swap(
                leg["pool"],state,authority,user_accounts[a],user_accounts[b],
                oracles[leg["pool"]],amount,threshold,
                a_to_b=source==a,amount_specified_is_input=True,
                oracle_writable=state["tick_spacing"]!=state["fee_tier_index_seed"]))
        elif venue=="raydium_cpmm":
            a,b=state["token_0_mint"],state["token_1_mint"]
            if (source,target)!=(a,b) and (source,target)!=(b,a):
                raise ValueError("CPMM onchain pool mints disagree")
            if state["token_0_program"]!=TOKEN_PROGRAM or state["token_1_program"]!=TOKEN_PROGRAM:
                raise ValueError("unsupported CPMM token program")
            # Raydium accounts are passed in INPUT/OUTPUT order, unlike Orca.
            instructions.append(build_cpmm(
                leg["pool"],state,authority,user_accounts[source],user_accounts[target],
                amount,threshold,input_is_token_0=source==a,exact_output=False,
                expected_mints=None))
        elif venue=="raydium_clmm":
            a,b=state["token_mint_0"],state["token_mint_1"]
            if (source,target) not in ((a,b),(b,a)):
                raise ValueError("CLMM onchain pool mints disagree")
            arrays=state.get("authenticated_tick_arrays")
            if not isinstance(arrays,(list,tuple)) or not 1<=len(arrays)<=5:
                raise ValueError("authenticated CLMM tick arrays required")
            if len(set(arrays))!=len(arrays) or any(
                    not isinstance(x,str) or not x for x in arrays):
                raise ValueError("invalid authenticated CLMM tick arrays")
            if oracles.get(leg["pool"])!=state.get("observation_key"):
                raise ValueError("authenticated CLMM observation mismatch")
            if state.get("token_program_0",TOKEN_PROGRAM)!=TOKEN_PROGRAM or state.get(
                    "token_program_1",TOKEN_PROGRAM)!=TOKEN_PROGRAM:
                raise ValueError("unsupported CLMM token program")
            instructions.append(build_clmm(
                leg["pool"],state,authority,user_accounts[source],user_accounts[target],
                amount,threshold,arrays,input_is_token_0=source==a,
                is_base_input=True))
        elif venue=="meteora_dlmm":
            x,y=state["token_x_mint"],state["token_y_mint"]
            if (source,target) not in ((x,y),(y,x)):
                raise ValueError("DLMM onchain pool mints disagree")
            oracle=oracles.get(leg["pool"])
            if not isinstance(oracle,str) or oracle!=state.get("oracle"):
                raise ValueError("authenticated DLMM oracle mismatch")
            arrays=state.get("authenticated_bin_arrays")
            if not isinstance(arrays,(list,tuple)) or not arrays:
                raise ValueError("authenticated DLMM bin arrays required")
            enriched=dict(state,input_mint=source,output_mint=target)
            instructions.append(build_dlmm(
                leg["pool"],enriched,authority,user_accounts[source],
                user_accounts[target],oracle,arrays,amount,threshold,
                input_is_x=source==x,
                bitmap_extension=state.get("bitmap_extension")))
        else:
            raise ValueError("unsupported executable venue: "+str(venue))
    return instructions
