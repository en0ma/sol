"""Execute one authenticated DAMM v2 signed swap on a local Surfpool fork.

Opt-in integration entry point. Requires pre-provisioned, fork-only funded SPL
user accounts. Never uses sendTransaction or a remote RPC. JSON artifacts are
nonactionable, and neither secrets nor serialized transactions are written.
"""
import argparse
import base64
import json
from pathlib import Path

from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.pumpswap_user_preflight import verify_user_accounts
from arb.meteora_damm_v2 import PROGRAM, decode, verify
from arb.meteora_damm_v2_swap import build_swap2
from arb.meteora_damm_v2_signed_runner import sign_and_simulate
from arb.token_vaults import TOKEN_PROGRAM, decode_token_account

SAFETY = {"actionable": False, "live_execution_approved": False, "broadcast": False}


def _account_snapshot(rpc, addresses, mints, owner):
    reply = call(rpc, "getMultipleAccounts", [
        addresses, {"encoding": "base64", "commitment": "confirmed"}])
    slot = reply.get("context", {}).get("slot")
    accounts = reply.get("value")
    if type(slot) is not int or slot < 0 or not isinstance(accounts, list) or len(accounts) != 2:
        raise ValueError("missing local token snapshot")
    amounts = []
    for entry, mint in zip(accounts, mints):
        if not isinstance(entry, dict) or entry.get("owner") != TOKEN_PROGRAM or entry.get("executable") is not False:
            raise ValueError("invalid local user token program")
        encoded = entry.get("data")
        if not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != "base64":
            raise ValueError("invalid local token account encoding")
        token = decode_token_account(base64.b64decode(encoded[0], validate=True))
        if token["mint"] != mint or token["authority"] != owner:
            raise ValueError("local user token mint or authority mismatch")
        amounts.append(token["amount_base_units"])
    return slot, amounts


def _signed_negative_control(rpc, *, pool, state, signer, input_account,
                             output_account, amount_in, input_is_a):
    """Excessive min-out must produce a failing, signature-verified fork simulation."""
    from solders.transaction import Transaction
    from solders.hash import Hash
    from arb.rpc import call
    ix = build_swap2(pool, state, str(signer.pubkey()), input_account,
                     output_account, amount_in, (1 << 64) - 1,
                     input_is_a=input_is_a)
    blockhash = call(rpc, "getLatestBlockhash")["value"]["blockhash"]
    signed = Transaction.new_signed_with_payer(
        [ix], signer.pubkey(), [signer], Hash.from_string(blockhash))
    signed.verify()
    result = call(rpc, "simulateTransaction", [
        base64.b64encode(bytes(signed)).decode("ascii"),
        {"encoding": "base64", "sigVerify": True,
         "replaceRecentBlockhash": False,
         "accounts": {"encoding": "base64",
                      "addresses": [input_account, output_account]}}])
    value = result.get("value") if isinstance(result, dict) else None
    if not isinstance(value, dict) or value.get("err") is None:
        raise ValueError("negative slippage control did not fail")
    return {"negative_slippage_failure_observed": True,
            "negative_error": str(value["err"]),
            "negative_signature": str(signed.signatures[0])}


def execute(rpc, *, pool, signer, input_account, output_account,
            amount_in, min_amount_out, input_is_a):
    local_rpc_only(rpc)
    if (type(input_is_a) is not bool or type(amount_in) is not int
            or type(min_amount_out) is not int
            or not 0 < amount_in < (1 << 64)
            or not 0 < min_amount_out < (1 << 64)):
        raise ValueError("invalid swap direction, amount or output floor")
    response = call(rpc, "getAccountInfo", [
        pool, {"encoding": "base64", "commitment": "confirmed"}])
    account = response.get("value")
    slot = response.get("context", {}).get("slot")
    if (type(slot) is not int or not isinstance(account, dict)
            or account.get("owner") != PROGRAM or account.get("executable") is not False):
        raise ValueError("DAMM v2 pool not authenticated on local fork")
    encoded = account.get("data")
    if not isinstance(encoded, list) or len(encoded) != 2 or encoded[1] != "base64":
        raise ValueError("DAMM v2 pool account encoding invalid")
    state = decode(base64.b64decode(encoded[0], validate=True))
    evidence = verify(rpc, pool, state)
    if evidence.get("slot", -1) < slot:
        raise ValueError("DAMM v2 verified pool evidence is stale")
    mint_in = state["token_a_mint"] if input_is_a else state["token_b_mint"]
    mint_out = state["token_b_mint"] if input_is_a else state["token_a_mint"]
    user = str(signer.pubkey())
    user_slot, amounts = _account_snapshot(
        rpc, [input_account, output_account], [mint_in, mint_out], user)
    if amounts[0] < amount_in:
        raise ValueError("insufficient fork-only input tokens")
    verify_user_accounts(rpc, user, input_account, output_account,
                         mint_in, mint_out, *amounts)
    positive = sign_and_simulate(
        rpc, pool=pool, state=state, evidence=evidence, payer=signer,
        user_input=input_account, user_output=output_account,
        initial_input=amounts[0], initial_output=amounts[1],
        amount_in=amount_in, min_amount_out=min_amount_out,
        input_is_a=input_is_a)
    if positive.get("signed_standalone_simulation_verified") is not True:
        raise ValueError("positive standalone simulation not verified")
    negative = _signed_negative_control(
        rpc, pool=pool, state=state, signer=signer,
        input_account=input_account, output_account=output_account,
        amount_in=amount_in, input_is_a=input_is_a)
    return {**positive, **negative, "user_snapshot_slot": user_slot,
            "positive_and_negative_controls_verified": True, **SAFETY}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rpc", default="http://127.0.0.1:8899")
    parser.add_argument("--pool", required=True)
    parser.add_argument("--signer-file", required=True,
                        help="Local fork-only ephemeral 64-byte keypair JSON; never stored in artifacts")
    parser.add_argument("--input-account", required=True)
    parser.add_argument("--output-account", required=True)
    parser.add_argument("--amount-in", type=int, required=True)
    parser.add_argument("--min-amount-out", type=int, required=True)
    parser.add_argument("--input-is-a", action="store_true")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    local_rpc_only(args.rpc)
    from solders.keypair import Keypair
    secret = json.loads(Path(args.signer_file).read_text())
    if not isinstance(secret, list) or len(secret) != 64 or any(
            type(v) is not int or not 0 <= v <= 255 for v in secret):
        raise ValueError("invalid local signer file")
    signer = Keypair.from_bytes(bytes(secret))
    destination = Path(args.output)
    try:
        report = execute(
            args.rpc, pool=args.pool, signer=signer,
            input_account=args.input_account, output_account=args.output_account,
            amount_in=args.amount_in, min_amount_out=args.min_amount_out,
            input_is_a=args.input_is_a)
    except Exception as exc:
        report = {"status": "UNVERIFIED", "reason": type(exc).__name__,
                  "signed_standalone_simulation_verified": False,
                  "positive_and_negative_controls_verified": False, **SAFETY}
        destination.write_text(json.dumps(report, indent=2) + "\n")
        raise
    report["status"] = "VERIFIED_LOCAL_FORK_STANDALONE"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "pool": report["pool"],
                      "broadcast": False}))


if __name__ == "__main__":
    main()
