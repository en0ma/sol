"""Bounded read-only legacy venue pool discovery on a local mainnet fork.

Uses exact mint-pair filters; never trusts returned program ownership without
subsequent independent account and vault authentication. An empty result is
not proof that a legacy swap venue is unavailable.
"""
from arb.rpc import call,RPCError
from arb.pumpswap_local_simulation import local_rpc_only
from arb.orca_whirlpool import SOL,USDC

LEGACY_FILTERS={
    "raydium_amm_v4":("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",752,400,432),
    "orca_token_swap_v1":("DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1",324,131,163),
}

def discover(rpc,venue,*,pairs=((SOL,USDC),),max_matches=8):
    local_rpc_only(rpc)
    if venue not in LEGACY_FILTERS or type(max_matches)is not int or not 1<=max_matches<=16:
        raise ValueError("unsupported discovery venue or candidate bound")
    program,size,offset_a,offset_b=LEGACY_FILTERS[venue]
    if not isinstance(pairs,(list,tuple)) or len(pairs)>4:
        raise ValueError("legacy discovery supports at most four mint pairs")
    result=[]
    for pair in pairs:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2 or pair[0]==pair[1]:
            raise ValueError("invalid legacy discovery mint pair")
        for left,right in (pair,tuple(reversed(pair))):
            if any(not isinstance(m,str) or not m for m in (left,right)):
                raise ValueError("invalid legacy mint")
            filters=[{"dataSize":size},
                     {"memcmp":{"offset":offset_a,"bytes":left}},
                     {"memcmp":{"offset":offset_b,"bytes":right}}]
            try:
                accounts=call(rpc,"getProgramAccounts",[
                    program,{"encoding":"base64","commitment":"confirmed","filters":filters}],
                    timeout=45,retries=0)
            except RPCError as exc:
                if "429" in str(exc) or "Too Many Requests" in str(exc):
                    raise ValueError("legacy discovery rate limited; no pool verification evidence") from exc
                raise
            if not isinstance(accounts,list) or len(accounts)>max_matches:
                raise ValueError("legacy candidate response unbounded or malformed")
            for item in accounts:
                account=item.get("account",{})
                address=item.get("pubkey")
                if (not isinstance(address,str) or account.get("owner")!=program
                        or account.get("executable") is not False):
                    raise ValueError("legacy discovery returned mismatched owner or address")
                if address not in result:
                    result.append(address)
                    if len(result)>max_matches:
                        raise ValueError("legacy discovery exceeds candidate bound")
    return result
