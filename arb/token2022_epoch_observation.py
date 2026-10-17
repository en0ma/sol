"""Bracket Token-2022 pool snapshots with chain epoch observations.

This only identifies fee schedules under a proven stable epoch. It does not
prove swap quoting or authorize execution.
"""
from arb.rpc import call
from arb.orca_token2022_validation import snapshot
from arb.token2022_extensions import fee_for_epoch

def _epoch_info(payload):
    if not isinstance(payload,dict):
        raise ValueError("missing epoch info")
    epoch=payload.get("epoch")
    slot=payload.get("absoluteSlot")
    if type(epoch) is not int or epoch<0 or type(slot) is not int or slot<0:
        raise ValueError("invalid epoch or absolute slot")
    return epoch,slot

def epoch_anchored_snapshot(rpc,address,max_slot_spread=32):
    if type(max_slot_spread) is not int or not 0<=max_slot_spread<=128:
        raise ValueError("invalid epoch observation bound")
    before=_epoch_info(call(rpc,"getEpochInfo",[{"commitment":"confirmed"}]))
    checked=snapshot(rpc,address)
    after=_epoch_info(call(rpc,"getEpochInfo",[{"commitment":"confirmed"}]))
    epoch=before[0]
    if before[0]!=after[0] or not before[1]<=checked["slot"]<=after[1]:
        raise ValueError("epoch observations do not bracket pool snapshot: "
                         f"before_epoch={before[0]} before_slot={before[1]} "
                         f"snapshot_slot={checked['slot']} after_epoch={after[0]} "
                         f"after_slot={after[1]}")
    if after[1]-before[1]>max_slot_spread:
        raise ValueError("epoch observation window too wide")
    configurations=[]
    for mint in checked["mint_accounts"]:
        cfg=mint["transfer_fee_config"]
        if cfg is None:
            configurations.append({"transfer_fee_configured":False})
        else:
            probe=fee_for_epoch(cfg,epoch,10000)
            configurations.append({"transfer_fee_configured":True,
                                   "schedule_epoch":probe["schedule_epoch"],
                                   "epoch":epoch,
                                   "basis_points":(cfg["newer"] if epoch>=cfg["newer"]["epoch"]
                                                   else cfg["older"])["basis_points"],
                                   "maximum_fee":(cfg["newer"] if epoch>=cfg["newer"]["epoch"]
                                                  else cfg["older"])["maximum_fee"]})
    return {**checked,"epoch_observation":{"epoch":epoch,
               "before_absolute_slot":before[1],"after_absolute_slot":after[1],
               "snapshot_slot":checked["slot"]},
            "mint_fee_schedules":configurations,
            "effective_fee_verified":False,"executable_quote":False,
            "actionable":False,"simulation_verified":False,"broadcast":False}
