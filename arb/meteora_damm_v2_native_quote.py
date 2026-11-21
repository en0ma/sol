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
    amount=reply.get("amount_out")
    if type(amount)is not int or not 0<amount<2**64:
        raise ValueError("official Meteora SDK returned invalid amount")
    return {**reply,"native_pricing_engine":"OFFICIAL_METEORA_RUST_SDK",
            "native_pricing_single_implementation":True,
            "actionable":False,"broadcast":False,"live_execution_approved":False}
