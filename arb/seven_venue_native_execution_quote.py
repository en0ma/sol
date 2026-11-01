"""Seven-venue native program *execution* quote via signed local Surfpool.

This produces an observed native program output, not an independent mathematical
quote prediction. Caller must supply independently owner/vault-authenticated
venue state, funded local SPL accounts and a locally funded signer. The only
RPC action is simulateTransaction on an explicit local read-only fork. No
airdrop, sendTransaction, account creation or mainnet transaction can occur.
"""
import base64
import hashlib

from arb.atomic_graph_coordinator import MAX_ATOMIC_LEGS
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account
from arb.venue_swap_adapter import build_leg

SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
VENUES=frozenset(("orca","raydium_cpmm","raydium_clmm",
                  "meteora_dlmm","meteora_damm_v2","pumpswap",
                  "raydium_amm_v4"))

def quote_signed_single_leg(rpc, *, venue, pool, state, evidence, signer,
                            input_token_account, output_token_account,
                            input_mint, output_mint,
                            initial_input_base_units, initial_output_base_units,
                            amount_in_base_units, min_output_base_units=1):
    """Execute exactly one signed native venue swap in local simulation.

    The unsigned pool quote and all original source contents remain separate.
    A native program may charge output/creator/transfer fees, so use actual
    post-SPL account amounts rather than guessing its protocol formula.
    """
    from solders.hash import Hash
    from solders.transaction import Transaction
    local_rpc_only(rpc)
    nums=(initial_input_base_units,initial_output_base_units,
          amount_in_base_units,min_output_base_units)
    if (venue not in VENUES
        or not isinstance(pool,str) or not 32<=len(pool)<=44
        or not isinstance(state,dict) or not isinstance(evidence,dict)
        or not all(isinstance(m,str) and 32<=len(m)<=44
                   for m in (input_mint,output_mint))
        or input_mint==output_mint
        or not all(isinstance(a,str) and 32<=len(a)<=44
                   for a in (input_token_account,output_token_account))
        or input_token_account==output_token_account
        or any(type(n) is not int or not 0<=n<2**64 for n in nums)
        or amount_in_base_units<=0 or min_output_base_units<=0
        or amount_in_base_units>initial_input_base_units):
        raise ValueError("incomplete funded single-leg native quote inputs")
    try:
        payer=str(signer.pubkey())
    except Exception as exc:
        raise ValueError("local signed fee payer required") from exc
    instruction=build_leg(
        venue,pool,state,evidence,payer,input_token_account,output_token_account,
        input_mint,output_mint,amount_in_base_units,min_output_base_units)
    block=call(rpc,"getLatestBlockhash")
    try:
        blockhash=Hash.from_string(block["value"]["blockhash"])
    except (ValueError,TypeError,KeyError) as exc:
        raise ValueError("local recent blockhash unavailable") from exc
    tx=Transaction.new_signed_with_payer(
        [instruction],signer.pubkey(),[signer],blockhash)
    tx.verify()
    wire=bytes(tx)
    if len(wire)>1232:
        raise ValueError("single-leg transaction exceeds Solana packet size")
    raw=call(rpc,"simulateTransaction",[
        base64.b64encode(wire).decode("ascii"),{
            "encoding":"base64","sigVerify":True,
            "replaceRecentBlockhash":False,
            "accounts":{"encoding":"base64",
                        "addresses":[input_token_account,output_token_account]}}])
    value=raw.get("value") if isinstance(raw,dict) else None
    if not isinstance(value,dict) or value.get("err") is not None:
        raise ValueError("native program signed simulation did not succeed")
    logs=value.get("logs")
    program=str(instruction.program_id)
    if (not isinstance(logs,list)
        or not any(isinstance(line,str) and
                   line.startswith("Program "+program+" invoke")
                   for line in logs)):
        raise ValueError("signed native program invocation not evidenced")
    rows=value.get("accounts")
    if not isinstance(rows,list) or len(rows)!=2:
        raise ValueError("native signed SPL account poststate unavailable")
    amounts=[]
    for row,mint in zip(rows,(input_mint,output_mint)):
        if (not isinstance(row,dict) or row.get("owner")!=TOKEN_PROGRAM
            or row.get("executable") is not False
            or not isinstance(row.get("data"),list)
            or len(row["data"])!=2 or row["data"][1]!="base64"):
            raise ValueError("missing original classic SPL poststate")
        state_bytes=base64.b64decode(row["data"][0],validate=True)
        token=decode_token_account(state_bytes)
        if token["mint"]!=mint:
            raise ValueError("native SPL poststate mint mismatch")
        amounts.append(token["amount_base_units"])
    spent=initial_input_base_units-amounts[0]
    received=amounts[1]-initial_output_base_units
    if (not 0<spent<=amount_in_base_units or
        not min_output_base_units<=received<2**64):
        raise ValueError("native program did not satisfy paid amount and floor")
    units=value.get("unitsConsumed")
    if type(units)is not int or not 0<units<=1400000:
        raise ValueError("native simulation compute observation unavailable")
    return {"status":"SIGNED_LOCAL_NATIVE_PROGRAM_OUTPUT_QUOTE_NOT_INDEPENDENT_PREDICTION",
            "venue":venue,"pool":pool,"input_mint":input_mint,
            "output_mint":output_mint,"amount_in_base_units":spent,
            "amount_out_base_units":received,
            "requested_input_base_units":amount_in_base_units,
            "signed_wire_sha256":hashlib.sha256(wire).hexdigest(),
            "first_signature":str(tx.signatures[0]),
            "observed_compute_units":units,
            "fee_lamports_paid":None,
            "native_swap_signed_simulation_verified":True,
            "native_math_independently_predicted":False,
            "signed_atomic_route_verified":False,
            "independent_mainnet_fee_verified":False,
            "net_profitability_verified":False,**SAFE}
