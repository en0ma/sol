"""Read-only active-venue decoder verification against synchronized RPC accounts.

A builder being importable is not evidence of a successful swap. This probe
reports those gates separately and never broadcasts transactions.
"""
import argparse
import base64
import importlib
import json
from pathlib import Path
from arb.rpc import call,RPCError
from arb.execution_target_matrix import TARGET_VENUES
from arb.onchain_pool_discovery import VENUES,verify as verify_pool
from arb.token_vaults import TOKEN_PROGRAM,decode_token_account

LEGACY={
    "raydium_amm_v4":("arb.raydium_amm_v4","675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
                       "base_mint","quote_mint","base_vault","quote_vault"),
    "orca_token_swap_v1":("arb.orca_token_swap_v1","DjVE6JNiYqPL2QXyCUUh8rNjHrbz9hXHNYt99MQ59qw1",
                          "token_a_mint","token_b_mint","token_a_vault","token_b_vault"),
}
BUILDERS={
    "orca":"arb.whirlpool_swap","raydium_cpmm":"arb.raydium_swap",
    "raydium_clmm":"arb.raydium_clmm_swap","meteora_dlmm":"arb.meteora_dlmm_swap",
    "meteora_damm_v2":"arb.meteora_damm_v2_swap",
    "pumpswap":"arb.pumpswap_swap","raydium_amm_v4":"arb.raydium_amm_v4_swap",
    "orca_token_swap_v1":"arb.orca_token_swap_v1_swap",
}

def verify_legacy(rpc,venue,address):
    module,program,mint_a,mint_b,vault_a,vault_b=LEGACY[venue]
    decoder=importlib.import_module(module).decode
    response=call(rpc,"getMultipleAccounts",[
        [address],{"encoding":"base64","commitment":"confirmed"}])
    accounts=response.get("value")
    slot=response.get("context",{}).get("slot")
    if type(slot)is not int or slot<0 or not isinstance(accounts,list) or len(accounts)!=1:
        raise ValueError("missing legacy pool snapshot")
    pool=accounts[0]
    if not pool or pool.get("owner")!=program or pool.get("executable") is not False:
        raise ValueError("legacy pool program owner mismatch")
    state=decoder(base64.b64decode(pool["data"][0],validate=True))
    extra=[state["market_id"]] if venue=="raydium_amm_v4" else []
    vault_response=call(rpc,"getMultipleAccounts",[
        [address,state[vault_a],state[vault_b],*extra],
        {"encoding":"base64","commitment":"confirmed","minContextSlot":slot}])
    values=vault_response.get("value")
    next_slot=vault_response.get("context",{}).get("slot")
    if type(next_slot)is not int or next_slot<slot or not isinstance(values,list) or len(values)!=3+len(extra):
        raise ValueError("incomplete legacy pool/vault snapshot")
    if not values[0] or values[0].get("owner")!=program or values[0].get("executable") is not False:
        raise ValueError("legacy pool owner changed")
    if decoder(base64.b64decode(values[0]["data"][0],validate=True))!=state:
        raise ValueError("legacy pool changed during verification")
    amounts=[]
    authorities=[]
    for vault,mint in zip(values[1:],(state[mint_a],state[mint_b])):
        if not vault or vault.get("owner")!=TOKEN_PROGRAM or vault.get("executable") is not False:
            raise ValueError("legacy pool vault owner mismatch")
        token=decode_token_account(base64.b64decode(vault["data"][0],validate=True))
        if token["mint"]!=mint or token["amount_base_units"]<=0:
            raise ValueError("legacy pool vault mint or reserve mismatch")
        amounts.append(token["amount_base_units"])
        authorities.append(token["authority"])
    if venue=="raydium_amm_v4":
        # OpenBook/Serum v3 MarketState is padded by five bytes on each
        # side; mint fields are at offsets 53 and 85 in raw account data.
        market=values[3]
        if (not market or market.get("owner")!=state["market_program"]
                or market.get("executable") is not False):
            raise ValueError("Raydium market owner mismatch")
        raw=base64.b64decode(market["data"][0],validate=True)
        if len(raw)<117 or raw[:5]!=b"serum":
            raise ValueError("unsupported Raydium OpenBook market layout")
        from arb.orca_whirlpool import b58
        if (b58(raw[53:85])!=state["base_mint"]
                or b58(raw[85:117])!=state["quote_mint"]):
            raise ValueError("Raydium market token mint mismatch")
    if venue=="orca_token_swap_v1":
        from solders.pubkey import Pubkey
        expected=str(Pubkey.create_program_address([
            bytes(Pubkey.from_string(address)),bytes([state["bump"]])],
            Pubkey.from_string(program)))
        if authorities!=[expected,expected]:
            raise ValueError("Orca Token Swap vault authority PDA mismatch")
    else:
        from solders.pubkey import Pubkey
        expected=str(Pubkey.find_program_address([
            b"amm authority"],Pubkey.from_string(program))[0])
        if authorities!=[expected,expected]:
            raise ValueError("Raydium AMM v4 vault authority PDA mismatch")
    return {"pool_decoder_verified":True,"vaults_verified":True,
            "slot":next_slot,"mints":[state[mint_a],state[mint_b]],
            "vault_base_units":amounts,"signed_swap_simulated":False}

def probe(rpc,registry,*,discover_legacy=False,public_raydium_candidates=(),
          public_orca_legacy_candidates=()):
    from arb.pumpswap_local_simulation import local_rpc_only
    # Allow only local fork RPC. This probe never queries public RPC directly.
    local_rpc_only(rpc)
    entries=registry.get("pools")
    if not isinstance(entries,list):
        raise ValueError("invalid pool registry")
    rows=[]
    for venue in TARGET_VENUES:
        module=BUILDERS[venue]
        try:
            builder_module=importlib.import_module(module)
            builder_implemented=any(callable(getattr(builder_module,name,None))
                                    for name in ("build","instruction","build_swap","build_swap2",
                                                 "build_swap_v2","build_instruction"))
        except ImportError:
            builder_implemented=False
        candidates=[entry["address"] for entry in entries
                    if isinstance(entry,dict) and entry.get("venue")==venue
                    and isinstance(entry.get("address"),str)]
        if venue=="raydium_amm_v4":
            candidates=list(dict.fromkeys(candidates+list(public_raydium_candidates)))
        elif venue=="orca_token_swap_v1":
            candidates=list(dict.fromkeys(candidates+list(public_orca_legacy_candidates)))
        evidence=None
        errors=[]
        discovered=[]
        if discover_legacy and venue in LEGACY and not candidates:
            try:
                from arb.legacy_pool_discovery import discover
                discovered=discover(rpc,venue)
            except (ValueError,KeyError,TypeError,TimeoutError,RPCError) as exc:
                errors.append("legacy discovery: "+str(exc))
        candidates=(candidates+discovered)[:8]
        for address in candidates:
            try:
                if venue in LEGACY:
                    evidence=verify_legacy(rpc,venue,address)
                else:
                    _,_,_,_,decoder=VENUES[venue]
                    account=call(rpc,"getAccountInfo",[
                        address,{"encoding":"base64","commitment":"confirmed"}])
                    value=account.get("value")
                    if not value or value.get("owner")!=VENUES[venue][0] or value.get("executable"):
                        raise ValueError("pool owner mismatch")
                    state=decoder(base64.b64decode(value["data"][0],validate=True))
                    evidence=verify_pool(rpc,venue,address,state)
                break
            except (ValueError,KeyError,TypeError,IndexError,ImportError,RPCError) as exc:
                errors.append(str(exc))
        rows.append({"venue":venue,"candidates_checked":len(candidates),
                     "discovered_candidate_addresses":discovered,
                     "decoder_onchain_verified":evidence is not None,
                     "builder_code_present":builder_implemented,
                     "builder_onchain_execution_verified":False,
                     "pool_evidence":evidence,
                     "errors":errors[:8]})
    return {"status":"SEVEN_VENUE_ONCHAIN_READONLY_PROBE",
            "archived_optional_venues":["orca_token_swap_v1"],
            "decoder_verified_count":sum(r["decoder_onchain_verified"] for r in rows),
            "builder_code_count":sum(r["builder_code_present"] for r in rows),
            "builder_execution_verified_count":0,"venues":rows,
            "actionable":False,"live_execution_approved":False,"broadcast":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--rpc",default="http://127.0.0.1:8899")
    parser.add_argument("--registry",default="arb/pool_registry.json")
    parser.add_argument("--discover-legacy",action="store_true")
    parser.add_argument("--public-raydium-candidates",default=None,
                        help="JSON array of untrusted API-discovered Raydium AMM v4 addresses")
    parser.add_argument("--public-orca-legacy-candidates",default=None,
                        help="JSON array of untrusted indexed Orca Token Swap v1 pool addresses")
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    public_candidates=[]
    if args.public_raydium_candidates:
        public_candidates=json.loads(Path(args.public_raydium_candidates).read_text())
        if not isinstance(public_candidates,list) or len(public_candidates)>16 or any(
                not isinstance(address,str) or not 32<=len(address)<=44
                for address in public_candidates):
            raise ValueError("invalid public Raydium candidate list")
    orca_candidates=[]
    if args.public_orca_legacy_candidates:
        orca_candidates=json.loads(Path(args.public_orca_legacy_candidates).read_text())
        if not isinstance(orca_candidates,list) or len(orca_candidates)>16 or any(
                not isinstance(address,str) or not 32<=len(address)<=44
                for address in orca_candidates):
            raise ValueError("invalid public Orca legacy candidate list")
    result=probe(args.rpc,json.loads(Path(args.registry).read_text()),
                 discover_legacy=args.discover_legacy,
                 public_raydium_candidates=public_candidates,
                 public_orca_legacy_candidates=orca_candidates)
    Path(args.output).write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in (
        "status","decoder_verified_count","builder_code_count",
        "builder_execution_verified_count","broadcast")}))
if __name__=="__main__":
    main()
