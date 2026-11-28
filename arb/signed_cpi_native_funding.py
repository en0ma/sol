"""Audit observed native funding from recorded positive simulation CPI.

This is separate from paid fees and profit. Surfpool can omit native
pre/post balances; no claim about full wallet debits or rent recovery is made.
The signed message is independently decoded by the calling audit.
"""
SAFE={"actionable":False,"broadcast":False,"live_execution_approved":False}
SYSTEM="11111111111111111111111111111111"
WSOL="So11111111111111111111111111111111111111112"

def audit_funding(response,keys,payer,economics):
    keys=[str(k) for k in keys]
    if not keys or keys[0]!=payer or len(set(keys))!=len(keys):
        raise ValueError("signed funding payer or key inventory mismatch")
    if response.get("err") is not None:
        raise ValueError("successful positive simulation required")
    groups=response.get("innerInstructions")
    if not isinstance(groups,list):
        raise ValueError("recorded funding CPI unavailable")
    created=[];transfers=[];unresolved=[];seen=set()
    for group in groups:
        index=group.get("index")
        if type(index) is not int or index<0 or index in seen:
            raise ValueError("ambiguous funding CPI group")
        seen.add(index)
        for entry in group["instructions"]:
            program=entry.get("programId")
            if program is None and type(entry.get("programIdIndex")) is int:
                p=entry["programIdIndex"]
                if not 0<=p<len(keys):
                    raise ValueError("funding program index invalid")
                program=keys[p]
            if program!=SYSTEM:
                continue
            parsed=entry.get("parsed")
            if not isinstance(parsed,dict) or not isinstance(parsed.get("info"),dict):
                unresolved.append({"leg_index":index,"reason":"unparsed system CPI"})
                continue
            info=parsed["info"];kind=parsed.get("type")
            if kind not in ("createAccount","createAccountWithSeed","transfer","transferWithSeed"):
                # No claim that unknown system operations cannot debit payer.
                if kind not in ("allocate","assign","allocateWithSeed","assignWithSeed"):
                    unresolved.append({"leg_index":index,"reason":"unsupported system CPI "+str(kind)})
                continue
            source=info.get("source")
            target=info.get("newAccount" if kind.startswith("createAccount") else "destination")
            value=info.get("lamports")
            if source not in keys or target not in keys or type(value) is not int or not 0<=value<2**64:
                raise ValueError("system funding CPI not bound to signed keys")
            if source!=payer:
                continue
            row={"leg_index":index,"source":source,"destination":target,"lamports":value,"kind":kind}
            if kind.startswith("createAccount"):
                if target==payer or any(r["destination"]==target for r in created):
                    raise ValueError("duplicate or self account initialization")
                if type(info.get("space")) is not int or info["space"]<0 or not isinstance(info.get("owner"),str):
                    raise ValueError("created account metadata unavailable")
                created.append({**row,"owner":info["owner"],"space":info["space"]})
            else:
                transfers.append(row)
    funding=sum(r["lamports"] for r in created)
    other=sum(r["lamports"] for r in transfers)
    before=response.get("preBalances");after=response.get("postBalances")
    observed=None
    if (isinstance(before,list) and isinstance(after,list)
            and len(before)==len(after)==len(keys)
            and all(type(v) is int and v>=0 for v in before+after)):
        observed=before[0]-after[0]
    recurring=economics.get("estimated_net_delta_start_mint_base_units")
    cash=(recurring-funding-other if type(recurring) is int
          and economics.get("start_mint")==WSOL and not unresolved else None)
    return {"status":"RECORDED_SYSTEM_CPI_FUNDING_ONLY",
            "created_accounts":created,"other_payer_system_transfers":transfers,
            "unresolved_system_cpi":unresolved,"observed_creation_funding_lamports":funding,
            "observed_other_outgoing_system_lamports":other,
            "recorded_payer_native_balance_delta_lamports":observed,
            "estimated_net_after_observed_funding_wsol_units":cash,
            "full_wallet_cost_reconciled":False,"rent_recovery_verified":False,
            "paid_network_fee_verified":False,"net_profit_verified":False,**SAFE}
