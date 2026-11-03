"""Fail-closed offline Clock alignment for authenticated permissioned DLMM swaps.

Never alters source pool data, never broadcasts, and never uses wall-clock time.
Only slot-activated permissioned LbPairs are supported by this path.
"""
import base64
from arb.meteora_dlmm import decode,PROGRAM
from arb.next_ten_fork_pool_probe import source_clock
from arb.pumpswap_local_simulation import local_rpc_only
from arb.rpc import call

def permissioned_dlmm_slot_requirement(fixture):
    if (not isinstance(fixture,dict) or
            fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL" or
            fixture.get("fixture_kind")!="AUTHENTICATED_FOUR_TO_SIX_HOP_SOURCE_ROUTE" or
            any(fixture.get(k)is not False for k in
                ("actionable","live_execution_approved","broadcast"))):
        raise ValueError("safe authenticated source fixture required")
    venues=fixture.get("route_venues")
    pools=fixture.get("route_pool_addresses")
    accounts=fixture.get("accounts")
    source_slot=fixture.get("state_accounts_observed_slot")
    if (not isinstance(venues,list) or not isinstance(pools,list)
            or len(venues)!=len(pools) or not isinstance(accounts,dict)
            or type(source_slot)is not int or source_slot<0):
        raise ValueError("source route identities and slot missing")
    restricted=[]
    for venue,pool in zip(venues,pools):
        if venue!="meteora_dlmm":
            continue
        record=accounts.get(pool)
        if not isinstance(record,dict) or record.get("owner")!=PROGRAM:
            raise ValueError("source DLMM owner missing or mismatched")
        raw=base64.b64decode(record["data"][0],validate=True)
        state=decode(raw)
        if state["pair_type"]!=1:
            continue
        if state["status"]!=0 or state["activation_type"]!=0:
            raise ValueError("permissioned DLMM pool disabled or non-slot activation unsupported")
        if source_slot<state["activation_point"]:
            raise ValueError("source snapshot predates permissioned DLMM activation")
        restricted.append({"pool":pool,"activation_point":state["activation_point"]})
    return source_slot,restricted

def align_permissioned_dlmm_clock(rpc,fixture):
    """Read back real SVM Clock after forward-only travel; reject failed parity."""
    local_rpc_only(rpc)
    from arb.source_snapshot_manifest import verify
    verify(fixture)
    target,pools=permissioned_dlmm_slot_requirement(fixture)
    if not pools:
        return {"status":"NO_PERMISSIONED_DLMM_CLOCK_ALIGNMENT_REQUIRED",
                "permissioned_pools":[]}
    before=source_clock(rpc)
    if before["slot"]<target:
        call(rpc,"surfnet_timeTravel",[{"absoluteSlot":target}])
    after=source_clock(rpc)
    if after["slot"]<target or after["slot"]<max(p["activation_point"] for p in pools):
        raise ValueError("permissioned DLMM offline Clock source-slot alignment failed")
    return {"status":"PERMISSIONED_DLMM_SOURCE_SLOT_ALIGNMENT_VERIFIED",
            "source_slot":target,"offline_before":before,"offline_after":after,
            "permissioned_pools":pools,
            "source_clock_timestamp_parity_claimed":False}
