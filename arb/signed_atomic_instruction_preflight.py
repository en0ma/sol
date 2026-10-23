"""Inspect signed legacy Solana transactions before cross-venue simulation.

Instruction order is proven by decoding the *signed transaction bytes*, not
from program invocation logs alone. Address lookup table messages are not
supported by this legacy-only verifier. This module never submits a transaction
and cannot prove the intermediate token flow or atomic rollback.
"""

def inspect_signed_legacy_order(signed_bytes,first_program,second_program,
                                *,intermediate_account=None):
    if not isinstance(signed_bytes,bytes) or not signed_bytes or len(signed_bytes)>1232:
        raise ValueError("missing signed legacy transaction or packet limit exceeded")
    if (not isinstance(first_program,str) or not first_program
            or not isinstance(second_program,str) or not second_program
            or first_program==second_program):
        raise ValueError("two distinct venue programs required")
    from solders.transaction import Transaction
    from solders.pubkey import Pubkey
    try:
        tx=Transaction.from_bytes(signed_bytes)
        message=tx.message
        keys=message.account_keys
        instructions=message.instructions
        programs=[str(keys[ix.program_id_index]) for ix in instructions]
    except (ValueError,TypeError,IndexError,AttributeError) as exc:
        raise ValueError("malformed or unsupported signed legacy transaction") from exc
    if programs.count(first_program)!=1 or programs.count(second_program)!=1:
        raise ValueError("expected exactly one instruction for each venue")
    first_index=programs.index(first_program)
    second_index=programs.index(second_program)
    if first_index>=second_index:
        raise ValueError("atomic venue instructions are reversed")
    if intermediate_account is not None:
        if not isinstance(intermediate_account,str) or not intermediate_account:
            raise ValueError("missing intermediate token account")
        try:
            key=Pubkey.from_string(intermediate_account)
        except ValueError as exc:
            raise ValueError("invalid intermediate token account") from exc
        if key not in keys:
            raise ValueError("intermediate account absent from signed transaction")
        index=keys.index(key)
        if (index not in instructions[first_index].accounts
                or index not in instructions[second_index].accounts):
            raise ValueError("both venue instructions must reference the intermediate account")
    return {"instruction_order_verified":True,
            "first_instruction_index":first_index,
            "second_instruction_index":second_index,
            "shared_intermediate_account_referenced":intermediate_account is not None,
            "intermediate_intra_transaction_consumption_verified":False,
            "rollback_failure_case_verified":False,
            "signed_atomic_simulation_verified":False,
            "actionable":False,"live_execution_approved":False,"broadcast":False}
