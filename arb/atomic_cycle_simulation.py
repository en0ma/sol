"""Fail-closed accounting for a signed, atomic multi-hop Surfpool simulation.

This verifier does not construct swap instructions or send transactions. It
accepts a signed serialized transaction, expected venue program IDs, and
pre-state SPL token balances for every distinct route mint.
"""
import base64
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account


def verify_atomic_cycle(rpc, signed_wire, tokens, venue_programs,
                        reference_fee_lamports=None):
    local_rpc_only(rpc)
    if not isinstance(signed_wire,bytes) or not signed_wire:
        raise ValueError("missing signed atomic transaction")
    if (not isinstance(tokens,list) or not 2<=len(tokens)<=4
            or not isinstance(venue_programs,list)
            or not 2<=len(venue_programs)<=4
            or any(not isinstance(p,str) or not p for p in venue_programs)):
        raise ValueError("invalid atomic route account or venue manifest")
    addresses=[];mints=[]
    for item in tokens:
        if (not isinstance(item,dict)
                or any(not isinstance(item.get(k),str) or not item[k]
                       for k in ("address","mint"))
                or type(item.get("before")) is not int
                or not 0<=item["before"]<1<<64):
            raise ValueError("invalid atomic route token pre-state")
        addresses.append(item["address"]);mints.append(item["mint"])
    if len(set(addresses))!=len(addresses) or len(set(mints))!=len(mints):
        raise ValueError("duplicate atomic route token accounts or mints")
    if reference_fee_lamports is not None and (type(reference_fee_lamports)is not int
            or reference_fee_lamports<0):
        raise ValueError("invalid reference fee")
    value=call(rpc,"simulateTransaction",[
        base64.b64encode(signed_wire).decode("ascii"),
        {"encoding":"base64","sigVerify":True,"replaceRecentBlockhash":False,
         "accounts":{"encoding":"base64","addresses":addresses}}])["value"]
    if value.get("err") is not None:
        raise ValueError("atomic route simulation failed: "+str(value["err"]))
    logs=value.get("logs")
    if not isinstance(logs,list):
        raise ValueError("missing atomic route logs")
    for program in set(venue_programs):
        if not any("Program "+program+" invoke" in line for line in logs):
            raise ValueError("atomic route venue invocation missing: "+program)
    accounts=value.get("accounts")
    if not isinstance(accounts,list) or len(accounts)!=len(tokens):
        raise ValueError("atomic route missing post-state")
    deltas={}
    for item,account in zip(tokens,accounts):
        if not isinstance(account,dict) or account.get("owner")!=TOKEN_PROGRAM:
            raise ValueError("unsupported atomic token account")
        data=account.get("data")
        if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
            raise ValueError("invalid atomic post-state encoding")
        state=decode_token_account(base64.b64decode(data[0],validate=True))
        if state["mint"]!=item["mint"]:
            raise ValueError("atomic post-state mint mismatch")
        deltas[item["mint"]]=state["amount_base_units"]-item["before"]
    start=tokens[0]["mint"]
    if any(deltas[mint]!=0 for mint in mints[1:]):
        raise ValueError("atomic route retained intermediate token balance change")
    units=value.get("unitsConsumed")
    if type(units)is not int or units<=0:
        raise ValueError("atomic route compute usage missing")
    gross=deltas[start]
    # A SOL-denominated fee cannot be subtracted from non-WSOL token units.
    WSOL="So11111111111111111111111111111111111111112"
    fee_comparable=start==WSOL and reference_fee_lamports is not None
    net_reference=gross-reference_fee_lamports if fee_comparable else None
    return {"status":"SIGNED_ATOMIC_CYCLE_SIMULATED",
            "simulation_verified":True,"venue_invocations_checked":len(set(venue_programs)),
            "hop_count":len(venue_programs),"mint_deltas":deltas,
            "intermediates_reconciled":True,"gross_start_token_base_units":gross,
            "units_consumed":units,"fee_reference_comparable":fee_comparable,
            "net_after_reference_fee_base_units":net_reference,
            "confirmed_profitable":False,
            "profitability_pending_full_fee_accounting":True,
            "actionable":False,"mainnet_broadcast":False}
