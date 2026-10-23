"""Two-phase DAMM v2 signed-swap fork reproduction.

Export on read-only upstream-backed Surfpool; never use account cheatcodes there.
Hydrate ONLY a separately started --offline Surfpool with explicit opt-in.
No mainnet transactions, persisted signer keys, or production execution.
"""
import base64
import json
import os
import sys
from pathlib import Path

from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.meteora_damm_v2 import PROGRAM, decode, verify
from arb.damm_v2_fork_execution import provision_offline_user, execute, SAFETY

LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
POOL = "8Pm2kZpnxD3hoMmt4bjStX2Pw2Z9abpbHzZxMPqxPmie"


def _fetch(rpc, addresses):
    reply = call(rpc, "getMultipleAccounts", [
        addresses, {"encoding": "base64", "commitment": "confirmed"}])
    values = reply.get("value") if isinstance(reply, dict) else None
    slot = reply.get("context", {}).get("slot") if isinstance(reply, dict) else None
    if type(slot) is not int or not isinstance(values, list) or len(values) != len(addresses):
        raise ValueError("fork fixture snapshot unavailable")
    if any(not isinstance(v, dict) for v in values):
        raise ValueError("missing fork fixture account")
    return slot, dict(zip(addresses, values))


def export(rpc, output, pool=POOL):
    local_rpc_only(rpc)
    # No surfnet methods are called by export.
    first = call(rpc, "getAccountInfo", [
        pool, {"encoding": "base64", "commitment": "confirmed"}])
    account = first.get("value") if isinstance(first, dict) else None
    if not isinstance(account, dict) or account.get("owner") != PROGRAM:
        raise ValueError("DAMM v2 pool unavailable on source fork")
    state = decode(base64.b64decode(account["data"][0], validate=True))
    evidence = verify(rpc, pool, state)
    if evidence.get("venue") != "meteora_damm_v2" or evidence.get("address") != pool:
        raise ValueError("source DAMM v2 pool unauthenticated")
    addresses = [pool, state["token_a_vault"], state["token_b_vault"],
                 state["token_a_mint"], state["token_b_mint"], PROGRAM]
    _, accounts = _fetch(rpc, addresses)
    program = accounts[PROGRAM]
    if program.get("owner") != LOADER or program.get("executable") is not True:
        raise ValueError("unsupported DAMM v2 executable program")
    from solders.pubkey import Pubkey
    program_bytes = base64.b64decode(program["data"][0], validate=True)
    if len(program_bytes) < 36 or program_bytes[:4] != bytes([2, 0, 0, 0]):
        raise ValueError("unsupported DAMM program loader state")
    programdata = str(Pubkey.from_bytes(program_bytes[4:36]))
    _, extra = _fetch(rpc, [programdata])
    accounts.update(extra)
    pd = accounts[programdata]
    pd_bytes = base64.b64decode(pd["data"][0], validate=True)
    if pd.get("owner") != LOADER or len(pd_bytes) < 49 or pd_bytes[:4] != bytes([3, 0, 0, 0]) or pd_bytes[45:49] != b"\\x7fELF":
        raise ValueError("DAMM executable programdata unavailable")
    payload = {"source": "READ_ONLY_MAINNET_BACKED_SURFPOOL",
               "pool": pool, "slot": evidence["slot"], "accounts": accounts,
               "verified": False, **SAFETY}
    Path(output).write_text(json.dumps(payload))
    return {"status": "DAMM_V2_READ_ONLY_FIXTURE_EXPORTED",
            "account_count": len(accounts), "slot": evidence["slot"], **SAFETY}


def offline(rpc, fixture, output, *, amount_in=1000, min_amount_out=1, input_is_a=True):
    local_rpc_only(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("separate offline Surfpool explicitly required")
    destination = Path(output)
    try:
        payload = json.loads(Path(fixture).read_text())
        if payload.get("source") != "READ_ONLY_MAINNET_BACKED_SURFPOOL":
            raise ValueError("invalid source fixture provenance")
        pool = payload["pool"]
        accounts = payload["accounts"]
        from solders.pubkey import Pubkey
        program = accounts[PROGRAM]
        raw = base64.b64decode(program["data"][0], validate=True)
        if program.get("owner") != LOADER or program.get("executable") is not True or raw[:4] != bytes([2, 0, 0, 0]):
            raise ValueError("invalid captured DAMM program")
        programdata = str(Pubkey.from_bytes(raw[4:36]))
        pd = accounts[programdata]
        elf = base64.b64decode(pd["data"][0], validate=True)
        if pd.get("owner") != LOADER or elf[:4] != bytes([3, 0, 0, 0]) or elf[45:49] != b"\\x7fELF":
            raise ValueError("invalid captured DAMM executable")
        # Only the dedicated offline process may receive synthetic account writes.
        for address, entry in accounts.items():
            if address in (PROGRAM, programdata):
                continue
            data = entry["data"]
            if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
                raise ValueError("invalid captured account payload")
            call(rpc, "surfnet_setAccount", [address, {
                "lamports": entry["lamports"],
                "data": base64.b64decode(data[0], validate=True).hex(),
                "owner": entry["owner"], "executable": entry["executable"]}])
        for offset in range(0, len(elf) - 45, 16384):
            call(rpc, "surfnet_writeProgram", [
                PROGRAM, elf[45 + offset:45 + offset + 16384].hex(), offset])
        signer, input_account, output_account = provision_offline_user(
            rpc, pool=pool, input_is_a=input_is_a, amount_in=amount_in)
        report = execute(rpc, pool=pool, signer=signer,
                         input_account=input_account, output_account=output_account,
                         amount_in=amount_in, min_amount_out=min_amount_out,
                         input_is_a=input_is_a)
        if report.get("positive_and_negative_controls_verified") is not True:
            raise ValueError("DAMM positive and negative controls unverified")
        report = {**report, "status": "ISOLATED_DAMM_V2_SIGNED_SWAP_VERIFIED",
                  "fixture_snapshot_slot": payload["slot"], **SAFETY}
    except Exception as exc:
        report = {"status": "UNVERIFIED", "reason": type(exc).__name__,
                  "diagnostic": str(exc)[:400],
                  "signed_standalone_simulation_verified": False,
                  "positive_and_negative_controls_verified": False, **SAFETY}
        destination.write_text(json.dumps(report, indent=2) + "\n")
        raise
    destination.write_text(json.dumps(report, indent=2) + "\n")
    return report


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["export", "offline"])
    parser.add_argument("path", help="Output fixture in export mode; input fixture in offline mode")
    parser.add_argument("--output", help="Required JSON report path for offline mode")
    parser.add_argument("--rpc", default="http://127.0.0.1:8899")
    parser.add_argument("--amount-in", type=int, default=1000)
    parser.add_argument("--min-amount-out", type=int, default=1)
    args = parser.parse_args()
    if args.mode == "export":
        report = export(args.rpc, args.path)
    else:
        if not args.output:
            parser.error("--output required in offline mode")
        report = offline(args.rpc, args.path, args.output,
                         amount_in=args.amount_in, min_amount_out=args.min_amount_out)
    print(json.dumps({"status": report["status"], "broadcast": False}))


if __name__ == "__main__":
    main()
