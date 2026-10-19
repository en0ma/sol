"""Offline-only initialized Token-2022 mint and signed transfer simulation.

Uses ephemeral keys and Surfpool local account setup. No mainnet RPC writes,
sendTransaction, or Orca swap execution. A synthetic mint is not a real pool mint.
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
from arb.orca_swap_v2_offline_transfer_accounting import reconcile_transfer_simulation
from arb.orca_swap_v2_offline_token_runtime_probe import (
    SYSTEM, TOKEN_2022, classify_token_runtime_simulation,
)

def initialized_mint_bytes(authority, decimals=6):
    if type(decimals) is not int or not 0 <= decimals <= 9:
        raise ValueError("invalid offline mint decimals")
    raw = bytearray(82)
    raw[0:4] = (1).to_bytes(4, "little")
    raw[4:36] = bytes(Pubkey.from_string(authority))
    raw[36:44] = (1000000).to_bytes(8, "little")
    raw[44] = decimals
    raw[45] = 1
    return bytes(raw)

def verify_token2022_transfer_logs(logs):
    if not isinstance(logs, list) or any(not isinstance(line, str) for line in logs):
        raise ValueError("missing Token-2022 runtime logs")
    invoked = any("Program " + TOKEN_2022 + " invoke" in line for line in logs)
    instruction = any("Program log: Instruction: TransferChecked" in line for line in logs)
    succeeded = any("Program " + TOKEN_2022 + " success" in line for line in logs)
    return invoked and instruction and succeeded

def run(rpc):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("explicit offline Surfpool opt-in required")
    signer = Keypair()
    authority = str(signer.pubkey())
    mint = str(Keypair().pubkey())
    raw_mint = initialized_mint_bytes(authority)
    call(rpc, "surfnet_setAccount", [mint, {
        "lamports": 2039280, "data": raw_mint.hex(),
        "owner": TOKEN_2022, "executable": False}])
    mint_response = call(rpc, "getAccountInfo", [
        mint, {"encoding": "base64", "commitment": "confirmed"}])
    mint_info = mint_response.get("value") if isinstance(mint_response, dict) else None
    encoded = mint_info.get("data") if isinstance(mint_info, dict) else None
    if (not isinstance(mint_info, dict) or mint_info.get("owner") != TOKEN_2022 or
            not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != "base64" or
            base64.b64decode(encoded[0], validate=True) != raw_mint):
        raise ValueError("initialized offline Token-2022 mint readback mismatch")
    plan = {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY",
            "required_accounts": [
                {"role": "token_owner_account_a", "mint": mint, "token_program": TOKEN_2022},
                {"role": "token_owner_account_b", "mint": mint, "token_program": TOKEN_2022}]}
    provision = provision_offline_fixture_accounts(
        rpc, plan, signer, amounts=(1000000, 0))
    call(rpc, "surfnet_setAccount", [authority, {
        "lamports": 1000000000, "data": "", "owner": SYSTEM, "executable": False}])
    latest = call(rpc, "getLatestBlockhash", [{"commitment": "confirmed"}])
    instruction = Instruction(Pubkey.from_string(TOKEN_2022),
        bytes([12]) + (1).to_bytes(8, "little") + bytes([6]),
        [AccountMeta(Pubkey.from_string(provision["addresses"][0]), False, True),
         AccountMeta(Pubkey.from_string(mint), False, False),
         AccountMeta(Pubkey.from_string(provision["addresses"][1]), False, True),
         AccountMeta(signer.pubkey(), True, False)])
    tx = Transaction.new_signed_with_payer(
        [instruction], signer.pubkey(), [signer],
        Hash.from_string(latest["value"]["blockhash"]))
    response = call(rpc, "simulateTransaction", [
        base64.b64encode(bytes(tx)).decode(),
        {"encoding": "base64", "sigVerify": True,
         "replaceRecentBlockhash": False, "commitment": "confirmed",
         "accounts": {"encoding": "base64", "addresses": provision["addresses"]}}])
    result = response.get("value") if isinstance(response, dict) else None
    status = classify_token_runtime_simulation(result)
    accounting = (reconcile_transfer_simulation(
        result, amount=1, initial_source=1000000, initial_destination=0)
        if status == "TOKEN_TRANSFER_SIMULATION_ACCEPTED" else None)
    logs = result.get("logs")
    program_executed = verify_token2022_transfer_logs(logs)
    if status != "TOKEN_TRANSFER_SIMULATION_ACCEPTED":
        raise ValueError("initialized offline Token-2022 transfer was not accepted")
    if accounting is None or accounting.get("post_token_balances_verified") is not True:
        raise ValueError("signed Token-2022 post-balances did not reconcile")
    if not program_executed:
        raise ValueError("Token-2022 TransferChecked program success logs missing")
    return {"status": status, "observed_simulation_error": result.get("err"),
            "transfer_accounting": accounting,
            "token_2022_execution_logs_verified": program_executed,
            "program_logs": logs,
            "compute_units_consumed": result.get("unitsConsumed"),
            "initialized_synthetic_mint_owner_verified": True,
            "synthetic_fixture_only": True,
            "signature_verification_requested": True,
            "token_runtime_transfer_accepted": status == "TOKEN_TRANSFER_SIMULATION_ACCEPTED",
            "orca_swap_simulation_verified": False,
            "signed_simulation_verified": False,
            "actionable": False, "executable_quote": False, "broadcast": False}

if __name__ == "__main__":
    print(json.dumps(run(os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899"))))
