"""Two-phase disposable Orca fork reproduction; no writes on the data-source fork.

export: read public authenticated fixture and executable program account state.
offline: require SURFPOOL_EXPLICITLY_OFFLINE=1, hydrate local Surfpool with
surfnet_setAccount, provision ephemeral user accounts, simulate only.
This is a diagnostic, not a claim of transferable mainnet account validity.
"""
import base64
import json
import os
import sys
from pathlib import Path
from solders.hash import Hash
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from arb.rpc import call
from arb.orca_whirlpool import PROGRAM
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc
from arb.orca_swap_v2_fork_signed_attempt import prepare_authenticated_attempt
from arb.orca_swap_v2_fixture_probe import CANDIDATE_POOL
from arb.orca_token2022_validation import snapshot
from arb.orca_token2022_quote_screen import directional_tick_array_candidates
from arb.orca_swap_v2_fixture_offline_provision import provision_offline_fixture_accounts

SYSTEM = "11111111111111111111111111111111"

def fetch_accounts(rpc, addresses):
    r = call(rpc, "getMultipleAccounts", [addresses, {"encoding": "base64", "commitment": "confirmed"}])
    values = r.get("value") if isinstance(r, dict) else None
    if not isinstance(values, list) or len(values) != len(addresses):
        raise ValueError("missing state export response")
    return dict(zip(addresses, values))

def export(rpc, output):
    require_loopback_rpc(rpc)
    obs = snapshot(rpc, CANDIDATE_POOL, include_ticks=True, include_oracle=True)
    pool = obs["pool"]
    addresses = [CANDIDATE_POOL, pool["token_vault_a"], pool["token_vault_b"],
                 *obs["mints"], PROGRAM]
    for direction in (True, False):
        candidate = directional_tick_array_candidates(pool, obs["tick_arrays"], direction)
        if not candidate["all_present"]:
            raise ValueError("authenticated directional tick coverage missing")
        addresses += candidate["addresses"]
    oracle = obs.get("oracle_evidence") or {}
    if oracle.get("address"):
        addresses.append(oracle["address"])
    accounts = fetch_accounts(rpc, list(dict.fromkeys(addresses)))
    program = accounts[PROGRAM]
    if not isinstance(program, dict) or program.get("executable") is not True:
        raise ValueError("Whirlpool program is not executable in fork")
    # UpgradeableLoaderState::Program = enum u32 tag 2, then programdata pubkey.
    raw = base64.b64decode(program["data"][0], validate=True)
    if program["owner"] == "BPFLoaderUpgradeab1e11111111111111111111111":
        if len(raw) < 36 or int.from_bytes(raw[:4], "little") != 2:
            raise ValueError("unexpected upgradeable program account layout")
        programdata = str(Pubkey.from_bytes(raw[4:36]))
        accounts.update(fetch_accounts(rpc, [programdata]))
        pd = accounts[programdata]
        if not isinstance(pd, dict):
            raise ValueError("UPSTREAM_PROGRAMDATA_MISSING")
        pd_raw = base64.b64decode(pd["data"][0], validate=True)
        elf_start = pd_raw.find(b"\\x7fELF", 45, min(len(pd_raw), 4096))
        if elf_start != 45:
            raise ValueError("UPSTREAM_PROGRAMDATA_ELF_NOT_AVAILABLE: bytes=" +
                             str(len(pd_raw)) + " elf_header_offset=" + str(elf_start) +
                             " first_64_hex=" + pd_raw[:64].hex())
    payload = {"pool": CANDIDATE_POOL, "snapshot_slot": obs["slot"],
               "observed": obs, "accounts": accounts,
               "source": "READ_ONLY_MAINNET_BACKED_SURFPOOL",
               "simulation_verified": False, "broadcast": False}
    Path(output).write_text(json.dumps(payload))
    return {"status": "AUTHENTICATED_STATE_EXPORTED", "count": len(accounts),
            "slot": obs["slot"], "broadcast": False}

def hydrate_and_attempt(rpc, input_path):
    require_loopback_rpc(rpc)
    if os.environ.get("SURFPOOL_EXPLICITLY_OFFLINE") != "1":
        raise ValueError("explicit offline-only Surfpool required")
    payload = json.loads(Path(input_path).read_text())
    if payload.get("source") != "READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("unsupported fixture provenance")
    program_info = payload["accounts"].get(PROGRAM)
    if not isinstance(program_info, dict):
        raise ValueError("captured Whirlpool executable program missing")
    program_raw = base64.b64decode(program_info["data"][0], validate=True)
    loader = "BPFLoaderUpgradeab1e11111111111111111111111"
    if program_info.get("owner") != loader or len(program_raw) < 36 or program_raw[:4] != bytes([2, 0, 0, 0]):
        raise ValueError("only authenticated upgradeable Whirlpool programs supported")
    programdata_address = str(Pubkey.from_bytes(program_raw[4:36]))
    programdata_info = payload["accounts"].get(programdata_address)
    if not isinstance(programdata_info, dict) or programdata_info.get("owner") != loader:
        raise ValueError("captured Whirlpool ProgramData missing")
    programdata_raw = base64.b64decode(programdata_info["data"][0], validate=True)
    if len(programdata_raw) < 49 or programdata_raw[:4] != bytes([3, 0, 0, 0]):
        raise ValueError("unexpected upgradeable ProgramData layout")
    elf = programdata_raw[45:]
    if elf[:4] != b"\\x7fELF":
        raise ValueError("captured Whirlpool program bytes do not begin with ELF")
    # Restore ordinary accounts first. Chunked program deployment is intentionally
    # handled via Surfpool's dedicated method, not oversized setAccount requests.
    for address, info in payload["accounts"].items():
        if address in (PROGRAM, programdata_address) or info is None:
            continue
        data = info.get("data")
        if not isinstance(data, list) or len(data) != 2 or data[1] != "base64":
            raise ValueError("invalid captured account encoding")
        raw = base64.b64decode(data[0], validate=True)
        call(rpc, "surfnet_setAccount", [address, {
            "lamports": info["lamports"], "data": raw.hex(),
            "owner": info["owner"], "executable": info["executable"]}])
    for offset in range(0, len(elf), 16384):
        call(rpc, "surfnet_writeProgram", [PROGRAM, elf[offset:offset + 16384].hex(), offset])
    signer = Keypair()
    plan = {"status": "USER_ACCOUNT_BINDING_PLAN_ONLY", "required_accounts": [
        {"role": "token_owner_account_a", "mint": mint, "token_program": mint_info["owner"]}
        for mint, mint_info in zip(payload["observed"]["mints"],
                                   payload["observed"]["mint_accounts"])]}
    plan["required_accounts"][1]["role"] = "token_owner_account_b"
    provision = provision_offline_fixture_accounts(
        rpc, plan, signer, amounts=(1000000, 0))
    call(rpc, "surfnet_setAccount", [str(signer.pubkey()), {
        "lamports": 1000000000, "data": "", "owner": SYSTEM, "executable": False}])
    instruction = prepare_authenticated_attempt(
        payload["observed"], signer, *provision["addresses"])
    latest = call(rpc, "getLatestBlockhash", [{"commitment": "confirmed"}])
    tx = Transaction.new_signed_with_payer(
        [instruction], signer.pubkey(), [signer],
        Hash.from_string(latest["value"]["blockhash"]))
    response = call(rpc, "simulateTransaction", [
        base64.b64encode(bytes(tx)).decode(),
        {"encoding": "base64", "sigVerify": True, "replaceRecentBlockhash": False,
         "commitment": "confirmed",
         "accounts": {"encoding": "base64", "addresses": provision["addresses"]}}])
    value = response.get("value") if isinstance(response, dict) else None
    if not isinstance(value, dict):
        raise ValueError("missing swap simulation result")
    logs = value.get("logs") or []
    program_invoked = any(("Program " + PROGRAM + " invoke") in line for line in logs)
    return {"status": ("OFFLINE_SWAP_PROGRAM_EXECUTED" if program_invoked else
                       "OFFLINE_SWAP_BLOCKED_BEFORE_PROGRAM"),
            "simulation_error": value.get("err"), "logs": logs,
            "units_consumed": value.get("unitsConsumed"),
            "post_accounts_returned": bool(value.get("accounts")),
            "orca_program_invoked": program_invoked,
            "synthetically_funded_users": True,
            "genuine_same_fork_user_accounts": False,
            "signed_simulation_verified": False, "actionable": False,
            "executable_quote": False, "broadcast": False}

if __name__ == "__main__":
    mode, path = sys.argv[1:3]
    rpc = os.environ.get("SOLANA_RPC_URL", "http://127.0.0.1:8899")
    if mode == "export":
        result = export(rpc, path)
    elif mode == "offline":
        result = hydrate_and_attempt(rpc, path)
    else:
        raise SystemExit("expected export or offline")
    print(json.dumps(result))
