"""Construct an unsigned Orca SwapV2 instruction candidate for local validation only.

This does not verify signer custody, token accounts, remaining-account extensions,
or execute/sign/simulate/broadcast anything. Caller must supply exact accounts.
"""
from solders.pubkey import Pubkey
from solders.instruction import AccountMeta, Instruction
from arb.orca_whirlpool import PROGRAM
from arb.orca_swap_v2_metas import validate_swap_v2_metas
from arb.orca_swap_v2_instruction_data import encode_swap_v2_data

def unsigned_swap_v2_candidate(metas,amount,other_amount_threshold,
                               sqrt_price_limit,amount_specified_is_input,a_to_b):
    validation=validate_swap_v2_metas(metas)
    # Parse every address before creating any instruction metadata.
    addresses=[]
    for meta in metas:
        try:
            addresses.append(Pubkey.from_string(meta["address"]))
        except (ValueError,TypeError) as exc:
            raise ValueError("invalid SwapV2 public key") from exc
    data=encode_swap_v2_data(amount,other_amount_threshold,sqrt_price_limit,
                             amount_specified_is_input,a_to_b)
    accounts=[AccountMeta(address,meta["is_signer"],meta["is_writable"])
              for address,meta in zip(addresses,metas)]
    instruction=Instruction(Pubkey.from_string(PROGRAM),data,accounts)
    return {"instruction":instruction,"validation":validation,
            "signatures_verified":False,"signed_simulation_verified":False,
            "actionable":False,"executable_quote":False,"broadcast":False}
