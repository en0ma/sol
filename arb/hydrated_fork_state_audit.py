"""Read-only hydrated Surfpool state audit before offline signing.

Compare each captured non-program state account to the actual local fork bytes
after hydration. A fork slot is not the original source slot; byte equality
does not establish independently authenticated mainnet provenance.
"""
import base64,hashlib
from arb.source_snapshot_manifest import verify
from arb.rpc import call
from arb.pumpswap_local_simulation import local_rpc_only
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def verify_hydrated_state(rpc,fixture,*,batch_size=64):
    local_rpc_only(rpc)
    verify(fixture)
    if type(batch_size)is not int or not 1<=batch_size<=100:
        raise ValueError("invalid bounded readback batch")
    selected=[]
    for address in fixture["state_account_addresses"]:
        src=fixture["accounts"][address]
        if src.get("executable") is False and src.get("owner")!="BPFLoaderUpgradeab1e11111111111111111111111":
            selected.append(address)
    if not selected:
        raise ValueError("no captured nonprogram accounts for readback")
    slots=[]
    for start in range(0,len(selected),batch_size):
        names=selected[start:start+batch_size]
        result=call(rpc,"getMultipleAccounts",[names,{"encoding":"base64","commitment":"confirmed"}])
        slot=result.get("context",{}).get("slot") if isinstance(result,dict) else None
        actual=result.get("value") if isinstance(result,dict) else None
        if type(slot)is not int or not isinstance(actual,list) or len(actual)!=len(names):
            raise ValueError("fork account readback missing contextual slot")
        slots.append(slot)
        for address,observed in zip(names,actual):
            source=fixture["accounts"][address]
            if not isinstance(observed,dict):
                raise ValueError("hydrated account absent")
            for field in ("owner","executable","lamports"):
                if observed.get(field)!=source.get(field):
                    raise ValueError("hydrated account metadata differs: "+address)
            a=observed.get("data");b=source.get("data")
            if (not isinstance(a,list) or len(a)!=2 or a[1]!="base64"
                or not isinstance(b,list) or len(b)!=2 or b[1]!="base64"
                or base64.b64decode(a[0],validate=True)!=base64.b64decode(b[0],validate=True)):
                raise ValueError("hydrated account bytes differ: "+address)
    if len(set(slots))!=1:
        raise ValueError("fork readback spans different slots")
    return {"status":"HYDRATED_FORK_ACCOUNT_BYTES_MATCH",
            "accounts_checked":len(selected),"fork_readback_slot":slots[0],
            "captured_source_slot":fixture["state_accounts_observed_slot"],
            "source_mainnet_slot_independently_attested":False,
            "signed_quote_accuracy_verified":False,**SAFE}
