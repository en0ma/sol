"""Signed SPL Token-2022 runtime probe on explicitly offline Surfpool only.

A synthetic historical mint may not be initialized on this offline validator.
This diagnostic never mistakes transport success or readback for token-runtime
acceptance, and never sends a transaction.
"""
import base64
import json
import os
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.instruction import Instruction, AccountMeta
from solders.transaction import Transaction
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_fixture_offline_provision import provision_offline_fixture_accounts
from arb.orca_swap_v2_fixture_offline_integration import (
    HISTORICAL_MINT_A, TOKEN_2022,
)

SYSTEM = "11111111111111111111111111111111"

def classify_token_runtime_simulation(value):
    if not isinstance(value, dict):
        raise ValueError("missing token runtime simulation result")
    err = value.get("err")
    if err is None:
        return "TOKEN_TRANSFER_SIMULATION_ACCEPTED"
    error_text = str(err).lower()
    if any(marker in error_text for marker in (
            "invalidprogramforexecution", "programaccountnotfound",
            "blockhashnotfound", "signaturefailure", "signature verification",
            "insufficientfundsforfee")):
        return "TOKEN_TRANSFER_SIMULATION_BLOCKED"
    return "TOKEN_TRANSFER_SIMULATION_REJECTED"

def run(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("explicit offline opt-in required")
    signer = Keypair()
    key = str(signer.pubkey())
    plan = {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY",
            "required_accounts": [
                {"role": "token_owner_account_a", "mint": HISTORICAL_MINT_A, "token_program": TOKEN_2022},
                {"role": "token_owner_account_b", "mint": HISTORICAL_MINT_A, "token_program": TOKEN_2022}]}
    provision = provision_offline_fixture_accounts(
        rpc, plan, signer, amounts=(1000000, 0))
    call(rpc, "surfnet_setAccount", [key, {
        "lamports": 1000000000, "data": "", "owner": SYSTEM, "executable": False}])
    payer = call(rpc, "getAccountInfo", [key, {"encoding": "base64"}])
    account = payer.get("value") if isinstance(payer, dict) else None
    if not isinstance(account, dict) or account.get("owner") != SYSTEM or account.get("lamports", 0) < 5000:
        raise ValueError("offline fee payer not verified")
    latest = call(rpc, "getLatestBlockhash", [{"commitment": "confirmed"}])
    blockhash = Hash.from_string(latest["value"]["blockhash"])
    # SPL Token TransferChecked: tag=12, amount (u64 LE), decimals (u8).
    # Historical mint decimals are NOT authenticated here: this may correctly
    # reject at runtime, which is captured as diagnostic evidence only.
    instruction = Instruction(
        Pubkey.from_string(TOKEN_2022),
        bytes([12]) + (1).to_bytes(8, "little") + bytes([0]),
        [AccountMeta(Pubkey.from_string(provision["addresses"][0]), False, True),
         AccountMeta(Pubkey.from_string(HISTORICAL_MINT_A), False, False),
         AccountMeta(Pubkey.from_string(provision["addresses"][1]), False, True),
         AccountMeta(signer.pubkey(), True, False)])
    tx = Transaction.new_signed_with_payer(
        [instruction], signer.pubkey(), [signer], blockhash)
    response = call(rpc, "simulateTransaction", [
        base64.b64encode(bytes(tx)).decode(),
        {"encoding": "base64", "sigVerify": True,
         "replaceRecentBlockhash": False, "commitment": "confirmed"}])
    value = response.get("value") if isinstance(response, dict) else None
    status = classify_token_runtime_simulation(value)
    return {
        "status": status,
        "observed_simulation_error": value.get("err"),
        "signature_verification_requested": True,
        "historical_mint_not_authenticated_on_offline_validator": True,
        "token_runtime_transfer_accepted": status == "TOKEN_TRANSFER_SIMULATION_ACCEPTED",
        "token_program_execution_evidence": status in (
            "TOKEN_TRANSFER_SIMULATION_ACCEPTED", "TOKEN_TRANSFER_SIMULATION_REJECTED"),
        "orca_swap_simulation_verified": False,
        "signed_simulation_verified": False,
        "actionable": False, "executable_quote": False, "broadcast": False,
    }

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
