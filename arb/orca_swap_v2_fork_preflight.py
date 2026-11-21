"""Fail-closed same-fork provenance preflight for diagnostic SwapV2 candidates.

Passing this check never authorizes signing or trading. In particular, a
mainnet quote and a Surfpool-local account read must not be conflated.
"""
def preflight_same_fork(quote, pool_evidence, user_evidence):
    failures=[]
    if not isinstance(quote,dict) or not isinstance(pool_evidence,dict) or not isinstance(user_evidence,dict):
        raise ValueError("preflight evidence must be dictionaries")
    fork=pool_evidence.get("fork_id")
    if not isinstance(fork,str) or not fork:
        failures.append("POOL_FORK_ID_MISSING")
    if quote.get("fork_id")!=fork or user_evidence.get("fork_id")!=fork:
        failures.append("FORK_PROVENANCE_MISMATCH")
    slots=[item.get("slot") for item in (quote,pool_evidence,user_evidence)]
    if any(type(slot) is not int or slot<0 for slot in slots):
        failures.append("UNVERIFIED_SLOTS")
    elif len(set(slots))!=1:
        failures.append("SNAPSHOT_SLOTS_MISMATCH")
    if not pool_evidence.get("pool_accounts_verified_same_fork",False):
        failures.append("POOL_ACCOUNTS_NOT_VERIFIED")
    if not user_evidence.get("owner_signature_control_verified",False):
        failures.append("SIGNER_CONTROL_NOT_VERIFIED")
    if not user_evidence.get("user_token_accounts_verified",False):
        failures.append("USER_TOKEN_ACCOUNTS_NOT_VERIFIED")
    if not quote.get("amounts_reconciled_against_fork_state",False):
        failures.append("QUOTE_NOT_RECONCILED")
    return {"preflight_evidence_complete":not failures,"failure_reasons":failures,
            "signed_simulation_verified":False,"actionable":False,
            "executable_quote":False,"broadcast":False}
