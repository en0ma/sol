"""Raydium CLMM independent integer exact-input curve quote, strictly one tick.

This candidate engine uses native Q64.64 and immutable authenticated source
bytes. It refuses dynamic fees, output-side fee variants and any price move
that crosses even an *uninitialized* tick. That deliberately excludes limit
order matching and liquidity-crossing until supported by the full protocol
integer engine. It is NOT official SDK parity and NOT signed acceptance.
"""
import argparse,json
from pathlib import Path

Q64=1<<64
FACTORS=(
0xfffcb933bd6fb800,0xfff97272373d4000,
0xfff2e50f5f657000,0xffe5caca7e10f000,
0xffcb9843d60f7000,0xff973b41fa98e800,
0xff2ea16466c9b000,0xfe5dee046a9a3800,
0xfcbe86c7900bb000,0xf987a7253ac65800,
0xf3392b0822bb6000,0xe7159475a2caf000,
0xd097f3bdfd2f2000,0xa9f746462d9f8000,
0x70d869a156f31c00,0x31be135f97ed3200,
0x9aa508b5b85a500,0x5d6af8dedc582c,
0x2216e584f5fa)
SAFE={"actionable":False,"broadcast":False,"signed_parity_verified":False,
      "registry_admission_approved":False,"official_sdk_parity_verified":False}

def sqrt_at_tick(tick):
    if type(tick) is not int or not -443636<=tick<=443636:
        raise ValueError("CLMM tick outside on-chain math bounds")
    abs_tick=abs(tick)
    ratio=Q64
    for index,factor in enumerate(FACTORS):
        if abs_tick&(1<<index):
            ratio=(ratio*factor)>>64
    if tick>0:
        ratio=((1<<128)-1)//ratio
    return ratio

def ceil_div(x,y):
    if type(x) is not int or type(y) is not int or x<0 or y<=0:
        raise ValueError("positive integer division required")
    return (x+y-1)//y

def quote_one_tick(state,config,amount,*,zero_for_one):
    if (not isinstance(state,dict) or not isinstance(config,dict)
            or type(amount) is not int or not 0<amount<1<<64
            or type(zero_for_one) is not bool):
        raise ValueError("authenticated native CLMM quote arguments missing")
    liquidity=int(state["liquidity"])
    price=int(state["sqrt_price_x64"])
    tick=state["tick_current"]
    fee=config["trade_fee_rate"]
    if (not 0<liquidity<1<<128 or not 0<price<1<<128 or
            type(tick) is not int or type(fee) is not int
            or not 0<=fee<1_000_000):
        raise ValueError("invalid CLMM source integer price/liquidity/config")
    if state["dynamic_fee_info_nonzero"] or state["fee_on"]!=0:
        raise ValueError("CLMM dynamic fee or output-side fee requires full native engine")
    deducted=ceil_div(amount*fee,1_000_000)
    net=amount-deducted
    if net<=0:
        raise ValueError("CLMM fee consumes the whole input")
    if zero_for_one:
        # token0 exact-in, rounded-up sqrt update and rounded-down token1
        new_price=ceil_div(liquidity*Q64*price,liquidity*Q64+net*price)
        if new_price<=sqrt_at_tick(tick):
            raise ValueError("CLMM input crosses tick: separate tick walk required")
        out=(liquidity*(price-new_price))//Q64
    else:
        # token1 exact-in, rounded-down sqrt update and token0 output
        new_price=price+(net*Q64)//liquidity
        if new_price>=sqrt_at_tick(tick+1):
            raise ValueError("CLMM input crosses tick: separate tick walk required")
        out=(liquidity*Q64*(new_price-price))//(new_price*price)
    if not 0<out<1<<64:
        raise ValueError("CLMM candidate output zero or overflow")
    return {"amount_in":amount,"fee":deducted,"output":out,
        "ending_sqrt_price_x64":str(new_price),
        "zero_for_one":zero_for_one,"crossed_ticks":0,
        "status":"NATIVE_INTEGER_SINGLE_TICK_CANDIDATE_ONLY",**SAFE}

def evaluate(tick_source,*,amounts=(10000,100000)):
    if (not isinstance(tick_source,dict)
            or tick_source.get("status")!="AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY"
            or not isinstance(tick_source.get("pools"),list)):
        raise ValueError("authenticated CLMM tick and config source required")
    results=[]
    for row in tick_source["pools"]:
        captured=row.get("tick_capture",{})
        import hashlib
        digest=hashlib.sha256(json.dumps(captured,sort_keys=True,
            separators=(",",":")).encode()).hexdigest()
        if digest!=row.get("tick_snapshot_sha256"):
            raise ValueError("CLMM authenticated tick source content digest mismatch")
        state=captured.get("synchronized_pool_state")
        config=captured.get("amm_config_source")
        if not isinstance(state,dict) or not isinstance(config,dict):
            raise ValueError("CLMM same-slot state and fee config missing")
        quotes=[];blocked=[]
        for zero_for_one in (True,False):
            for amount in amounts:
                try:
                    quotes.append(quote_one_tick(state,config,amount,
                                               zero_for_one=zero_for_one))
                except (ValueError,TypeError,KeyError) as exc:
                    blocked.append({"zero_for_one":zero_for_one,
                        "amount_in":amount,"reason":str(exc),
                        "status":"UNVERIFIED_CLMM_TICK_WALK_REQUIRED"})
        results.append({"pool":row["pool"],"snapshot_sha256":row["tick_snapshot_sha256"],
            "tick_source_slot":captured["tick_array_source_slot"],
            "quotes":quotes,"blocked":blocked,
            "native_pricing_verified":False})
    return {"venue":"raydium_clmm",
        "status":"CLMM_SINGLE_TICK_NATIVE_CANDIDATES_NOT_SDK_VERIFIED",
        "pools":results,"native_pricing_verified":False,**SAFE}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tick-source",required=True)
    p.add_argument("--output",required=True)
    args=p.parse_args()
    report=evaluate(json.loads(Path(args.tick_source).read_text()))
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"status":report["status"],
        "candidates":sum(len(r["quotes"]) for r in report["pools"]),
        "blocked":sum(len(r["blocked"]) for r in report["pools"])}))
if __name__=="__main__":main()
