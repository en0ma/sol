"""Read and verify Raydium CPMM AmmConfig fee parameters from Solana RPC.

See raydium-cp-swap programs/cp-swap/src/states/config.rs.
Quotes using the config are indicative: creator fees may be applied
on input or output according to pool-specific state and runtime version.
"""
import base64,hashlib
from arb.rpc import call
from arb.raydium_cpmm import PROGRAM
from arb.cpmm_quote import FEE_DENOMINATOR
from arb.onchain_pool_discovery import VENUES
DISC=hashlib.sha256(b"account:AmmConfig").digest()[:8]
CONFIG_SIZE=236

def decode_amm_config(raw):
    if type(raw) is not bytes or len(raw)!=CONFIG_SIZE or raw[:8]!=DISC:
        raise ValueError("invalid Raydium CPMM AmmConfig length/discriminator")
    u64=lambda offset:int.from_bytes(raw[offset:offset+8],"little")
    index=int.from_bytes(raw[10:12],"little")
    trade=u64(12);protocol=u64(20);fund=u64(28);creator=u64(108)
    if (trade+creator>=FEE_DENOMINATOR or protocol+fund>FEE_DENOMINATOR):
        raise ValueError("invalid CPMM fee rates")
    return {"bump":raw[8],"disable_create_pool":bool(raw[9]),"index":index,
            "trade_fee_rate_ppm":trade,"protocol_fee_rate_ppm":protocol,
            "fund_fee_rate_ppm":fund,"creator_fee_rate_ppm":creator}

def read_pool_config(rpc,pool):
    if pool.get("venue")!="raydium_cpmm" or not pool.get("verified"):
        raise ValueError("pool must be verified Raydium CPMM")
    # Independently verify pool/config linkage; do not accept user-supplied config.
    from arb.raydium_cpmm import decode
    pool_address=pool["address"]
    info=call(rpc,"getAccountInfo",[pool_address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not info or info.get("owner")!=PROGRAM:raise ValueError("invalid CPMM pool owner")
    state=decode(base64.b64decode(info["data"][0],validate=True))
    if sorted((state["token_0_mint"],state["token_1_mint"]))!=sorted(pool["mints"]):
        raise ValueError("CPMM mint mismatch")
    config_address=state["amm_config"]
    account=call(rpc,"getAccountInfo",[config_address,{"encoding":"base64","commitment":"confirmed"}]).get("value")
    if not account or account.get("owner")!=PROGRAM or account.get("executable"):
        raise ValueError("invalid CPMM config owner")
    cfg=decode_amm_config(base64.b64decode(account["data"][0],validate=True))
    from solders.pubkey import Pubkey
    expected,bump=Pubkey.find_program_address([b"amm_config",cfg["index"].to_bytes(2,"big")],Pubkey.from_string(PROGRAM))
    if str(expected)!=config_address or bump!=cfg["bump"]:
        raise ValueError("CPMM config PDA mismatch")
    return {**cfg,"pool":pool_address,"config_address":config_address,
            "fee_verified_onchain":True,"creator_fee_placement_verified":False}
