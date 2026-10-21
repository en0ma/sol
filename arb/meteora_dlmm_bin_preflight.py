"""Read-only Meteora DLMM active-bin array evidence for verified pools.

This preflight is NOT a swap quote or an executable adapter. It verifies the
program-owned active bin array PDA and refuses to infer adjacent liquidity.
No RPC method here may mutate account state.
"""
import base64
import hashlib
from solders.pubkey import Pubkey
from arb.meteora_dlmm import PROGRAM, decode
from arb.rpc import call
from arb.orca_swap_v2_local_token_accounts import require_loopback_rpc

BIN_ARRAY_SIZE=70
BIN_ARRAY_DISC=hashlib.sha256(b"account:BinArray").digest()[:8]

def active_bin_array_index(active_id):
    if type(active_id) is not int or not -(1<<31)<=active_id<(1<<31):
        raise ValueError("invalid signed active bin id")
    return active_id//BIN_ARRAY_SIZE

def bin_array_pda(pool, index):
    if type(index) is not int or not -(1<<63)<=index<(1<<63):
        raise ValueError("invalid bin array index")
    program=Pubkey.from_string(PROGRAM)
    pair=Pubkey.from_string(pool)
    return str(Pubkey.find_program_address([
        b"bin_array",bytes(pair),index.to_bytes(8,"little",signed=True)],program)[0])

def check_active_bin_array(rpc,pool):
    require_loopback_rpc(rpc)
    account=call(rpc,"getAccountInfo",[pool,{"encoding":"base64","commitment":"confirmed"}])["value"]
    if not account or account.get("owner")!=PROGRAM or account.get("executable"):
        raise ValueError("missing genuine Meteora DLMM pair account")
    state=decode(base64.b64decode(account["data"][0],validate=True))
    idx=active_bin_array_index(state["active_id"])
    address=bin_array_pda(pool,idx)
    candidate=call(rpc,"getAccountInfo",[address,{"encoding":"base64","commitment":"confirmed"}])["value"]
    report={"venue":"meteora_dlmm","pool":pool,"active_bin_id":state["active_id"],
            "active_bin_array_index":idx,"active_bin_array_pda":address,
            "swap_instruction_supported":False,"atomic_simulation_verified":False,
            "actionable":False,"broadcast":False}
    if not candidate:
        return dict(report,status="ACTIVE_BIN_ARRAY_ABSENT")
    if candidate.get("owner")!=PROGRAM or candidate.get("executable"):
        raise ValueError("active bin array owner/executable mismatch")
    raw=base64.b64decode(candidate["data"][0],validate=True)
    if len(raw)<48 or raw[:8]!=BIN_ARRAY_DISC:
        raise ValueError("active bin array discriminator/length mismatch")
    actual_index=int.from_bytes(raw[8:16],"little",signed=True)
    actual_pair=str(Pubkey.from_bytes(raw[16:48]))
    if actual_index!=idx or actual_pair!=pool:
        raise ValueError("active bin array index or parent pool mismatch")
    return dict(report,status="ACTIVE_BIN_ARRAY_AUTHENTICATED",
                active_bin_array_byte_length=len(raw))
