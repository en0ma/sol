"""Single Meteora DAMM v2 native pricing engine: official revision-pinned Rust SDK.

Python marshals authenticated source Pool bytes and fork Clock only. It does
NOT implement swap math, dynamic fees, curves or a second pricing engine.
"""
import base64,json,subprocess
from arb.meteora_damm_v2 import PROGRAM,decode
DEFAULT_BINARY="tools/meteora_damm_v2_reference/target/release/sol-meteora-damm-v2-official-reference"

def quote_pool_account(account,*,mint_in,amount_in,fork_unix_timestamp,
                       fork_clock_slot,binary=DEFAULT_BINARY):
    if (not isinstance(account,dict) or account.get("owner")!=PROGRAM or
            account.get("executable") is not False):
        raise ValueError("authenticated Meteora pool owner required")
    data=account.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("source pool bytes missing")
    raw=base64.b64decode(data[0],validate=True)
    state=decode(raw)
    if (mint_in not in (state["token_a_mint"],state["token_b_mint"]) or
            type(amount_in)is not int or not 0<amount_in<2**64 or
            type(fork_unix_timestamp)is not int or fork_unix_timestamp<=0 or
            type(fork_clock_slot)is not int or fork_clock_slot<=0):
        raise ValueError("Meteora exact input, pool mint, or signed Clock invalid")
    request={"pool_data_base64":data[0],"amount_in":amount_in,
             "input_is_a":mint_in==state["token_a_mint"],
             "fork_unix_timestamp":fork_unix_timestamp,
             "fork_clock_slot":fork_clock_slot}
    try:
        result=subprocess.run([binary],input=json.dumps(request),text=True,
                              capture_output=True,timeout=60,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError("official Meteora native quote unavailable") from exc
    if result.returncode:
        raise ValueError("official Meteora SDK rejected source pool: "+result.stderr[-250:])
    reply=json.loads(result.stdout)
    if (not isinstance(reply,dict) or reply.get("status")!="OFFICIAL_METEORA_DAMM_V2_EXACT_INPUT"
            or reply.get("official_repository_revision")!="5398b5c7c534de014091132da37c6478cce671a8"
            or type(reply.get("amount_in")) is not int or reply["amount_in"]!=amount_in
            or type(reply.get("amount_left")) is not int or reply["amount_left"]!=0
            or any(reply.get(k) is not False for k in ("actionable","broadcast","live_execution_approved"))):
        raise ValueError("official Meteora SDK result incomplete or inconsistent")
    amount=reply.get("amount_out")
    if type(amount)is not int or not 0<amount<2**64:
        raise ValueError("official Meteora SDK returned invalid amount")
    return {**reply,"native_pricing_engine":"OFFICIAL_METEORA_RUST_SDK",
            "native_pricing_single_implementation":True,
            "actionable":False,"broadcast":False,"live_execution_approved":False}


def bounded_dust_input_candidates(*,sqrt_price,input_is_a,amount_in,input_vault_balance):
    """Choose integer research sizes, not a second DAMM quote engine."""
    if (type(input_is_a) is not bool or any(type(x) is not int for x in
            (sqrt_price,amount_in,input_vault_balance)) or not 0<sqrt_price<2**128
            or not 0<amount_in<2**64 or not 0<input_vault_balance<2**64):
        raise ValueError("invalid DAMM dust-sizing inputs")
    square=sqrt_price*sqrt_price;scale=1<<128
    numerator,denominator=(square,scale) if input_is_a else (scale,square)
    # Limit the intervention to low output denomination, not slippage
    # failures caused by an unverified liquidity or fee regime.
    if amount_in*numerator>=denominator:
        return []
    maximum=min(2**64-1,amount_in*1000,input_vault_balance//10000)
    sizes=[]
    for target in (16,32):
        candidate=(target*denominator+numerator-1)//numerator
        if amount_in<candidate<=maximum and candidate not in sizes:
            sizes.append(candidate)
    return sizes


def source_dust_size_plan(fixture,*,amount_in):
    """Authenticate first-leg original price and SPL input reserve."""
    from arb.fixture_quote_execution_pipeline import extract_pool_states
    from arb.token_vaults import TOKEN_PROGRAM,decode_token_account
    from arb.meteora_damm_v2_swap import POOL_AUTHORITY
    safe={"actionable":False,"broadcast":False,"live_execution_approved":False}
    rows=extract_pool_states(fixture)
    if not rows or rows[0]["venue"]!="meteora_damm_v2" or any(fixture.get(k) is not False for k in safe):
        raise ValueError("first-leg authenticated DAMM source required")
    row=rows[0];state=row["decoded_pool_state"];mint=fixture["route_mints"][0]
    direction=mint==state["token_a_mint"]
    if mint not in (state["token_a_mint"],state["token_b_mint"]):
        raise ValueError("DAMM dust-sizing mint mismatch")
    vault=state["token_a_vault" if direction else "token_b_vault"]
    if vault not in fixture["state_account_addresses"]:
        raise ValueError("DAMM dust-sizing source vault absent")
    account=fixture["accounts"][vault]
    if account.get("owner")!=TOKEN_PROGRAM or account.get("executable") is not False:
        raise ValueError("DAMM dust-sizing vault owner mismatch")
    data=account.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("DAMM dust-sizing vault encoding mismatch")
    reserve=decode_token_account(base64.b64decode(data[0],validate=True))
    if reserve["mint"]!=mint or reserve["authority"]!=POOL_AUTHORITY:
        raise ValueError("DAMM dust-sizing vault mint or authority mismatch")
    candidates=bounded_dust_input_candidates(sqrt_price=state["sqrt_price"],input_is_a=direction,
        amount_in=amount_in,input_vault_balance=reserve["amount_base_units"])
    return {"status":"SOURCE_DAMM_DUST_SIZE_HINT_ONLY","pool":row["address"],
        "source_slot":row["snapshot_slot"],"manifest_sha256":fixture["state_account_manifest_sha256"],
        "input_mint":mint,"input_base_units":amount_in,"input_vault":vault,
        "input_vault_base_units":reserve["amount_base_units"],"sqrt_price":str(state["sqrt_price"]),
        "candidate_amounts":candidates,"protocol_exact_verified":False,**safe}
