"use strict";
/** Read-only official Raydium concentrated-liquidity SDK reference quotes.
 * Loads *exactly* the independently authenticated pool, tick-array, config
 * bytes supplied in the source artifact. No API prices, no mainnet quoting
 * against a later slot, no wallet construction, no simulation or broadcast.
 */
const fs=require("fs"),crypto=require("crypto");
const ray=require("@raydium-io/raydium-sdk-v2");
const {PublicKey}=require("@solana/web3.js");
const BN=require("bn.js");

function demand(cond,why){if(!cond)throw Error(why);}
function canonical(v) {
  if(Array.isArray(v))return "["+v.map(canonical).join(",")+"]";
  if(v&&typeof v==="object")return "{"+Object.keys(v).sort().map(k=>JSON.stringify(k)+":"+canonical(v[k])).join(",")+"}";
  return JSON.stringify(v);
}
function decode(label,blob) {
  demand(typeof blob==="string"&&blob.length>10,"missing "+label+" source bytes");
  const data=Buffer.from(blob,"base64");
  demand(data.toString("base64")===blob,"noncanonical "+label+" source bytes");
  return data;
}
function quotePool(row,native) {
  demand(native.pool===row.pool&&native.snapshot_sha256===row.tick_snapshot_sha256,
    "SDK/native authenticated tick SHA-256 mismatch");
  const digest=crypto.createHash("sha256").update(canonical(row.tick_capture)).digest("hex");
  demand(digest===row.tick_snapshot_sha256,"SDK original tick source integrity mismatch");
  demand(ray.PoolInfoLayout&&ray.ClmmConfigLayout&&ray.TickArrayLayout&&ray.PoolUtils,
    "official Raydium SDK layout or quote exports not available");
  const source=row.tick_capture;
  const pool=ray.PoolInfoLayout.decode(decode("PoolState",source.tick_array_pool_data_base64));
  const config=ray.ClmmConfigLayout.decode(decode("AmmConfig",
    source.amm_config_source.account_base64));
  const tickArrayCache={};
  for(const entry of source.tick_arrays) {
    if(!entry.present)continue;
    const parsed=ray.TickArrayLayout.decode(decode("TickArrayState",entry.account_base64));
    demand(parsed.startTickIndex===entry.start_tick_index,
      "SDK tick array index disagrees with verified source");
    parsed.address=new PublicKey(entry.address);
    tickArrayCache[entry.start_tick_index]=parsed;
  }
  demand(Object.keys(tickArrayCache).length===source.arrays_present,
    "SDK tick array cache incomplete");
  const info={
    id:new PublicKey(row.pool),
    programId:new PublicKey("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"),
    mintA:{address:pool.mintA.toBase58()},
    mintB:{address:pool.mintB.toBase58()},
    accInfo:pool,
    ammConfig:config
  };
  // Valid only for the source's bounded central 1024-array bitmap.
  // Extension is empty; a requested outside-range array must be rejected
  // separately instead of interpolating from a different RPC slot.
  const zeroExtension={
    negativeTickArrayBitmap:Array.from({length:14},
      ()=>Array.from({length:8},()=>new BN(0))),
    positiveTickArrayBitmap:Array.from({length:14},
      ()=>Array.from({length:8},()=>new BN(0)))
  };
  const out=[];
  for(const nativeQuote of native.quotes) {
    const inputMint=nativeQuote.zero_for_one?pool.mintA:pool.mintB;
    const amount=new BN(String(nativeQuote.amount_in));
    const computed=ray.PoolUtils.getOutputAmountAndRemainAccounts(
      info,zeroExtension,tickArrayCache,inputMint,amount,0);
    demand(computed.expectedAmountOut&&computed.expectedAmountOut.gt(new BN(0)),
      "official SDK zero output");
    const official=computed.expectedAmountOut.toString();
    const candidate=String(nativeQuote.output);
    out.push({input_mint:inputMint.toBase58(),
      output_mint:(nativeQuote.zero_for_one?pool.mintB:pool.mintA).toBase58(),
      zero_for_one:nativeQuote.zero_for_one,amount_in:nativeQuote.amount_in,
      native_integer_output:candidate,official_sdk_output:official,
      expected_fee_native:nativeQuote.fee,
      official_fee:computed.feeAmount.toString(),
      remaining_tick_arrays:computed.remainingAccounts.map(k=>k.toBase58()),
      all_trade:computed.allTrade===true,
      signed_parity_verified:false,
      status:official===candidate?"OFFICIAL_SDK_NATIVE_SINGLE_TICK_EXACT":
        "OFFICIAL_SDK_NATIVE_SINGLE_TICK_MISMATCH"});
  }
  return {pool:row.pool,source_slot:source.tick_array_source_slot,
    tick_snapshot_sha256:row.tick_snapshot_sha256,
    trials:out,matched:out.filter(t=>t.status==="OFFICIAL_SDK_NATIVE_SINGLE_TICK_EXACT").length};
}
function main() {
  demand(process.argv.length===5,
    "usage node tools/raydium_clmm_official_sdk_oracle.js TICK-SOURCE.json NATIVE.json OUTPUT.json");
  const tick=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
  const native=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));
  demand(tick.venue==="raydium_clmm"&&native.venue==="raydium_clmm"&&
    tick.status==="AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY"&&
    native.status==="CLMM_SINGLE_TICK_NATIVE_CANDIDATES_NOT_SDK_VERIFIED",
    "source/native CLMM candidate reports untrusted");
  demand(Array.isArray(tick.pools)&&tick.pools.length===native.pools.length,
    "SDK/native number of authenticated CLMM pools differs");
  const indexed=new Map(native.pools.map(r=>[r.pool,r]));
  demand(indexed.size===tick.pools.length,"duplicate CLMM candidate pool");
  const pools=tick.pools.map(row=>quotePool(row,indexed.get(row.pool)));
  const exact=pools.every(p=>p.trials.length===4&&p.matched===4);
  const result={venue:"raydium_clmm",
    status:exact?"RAYDIUM_CLMM_NATIVE_SDK_SINGLE_TICK_EXACT":
      "RAYDIUM_CLMM_NATIVE_SDK_CANDIDATE_MISMATCH",
    official_sdk_native_parity_verified:exact,
    signed_parity_verified:false,registry_admission_approved:false,
    actionable:false,broadcast:false,pools};
  fs.writeFileSync(process.argv[4],JSON.stringify(result,null,2)+"\n");
  console.log(JSON.stringify({status:result.status,pools:pools.length,
    exact_trials:pools.reduce((sum,p)=>sum+p.matched,0)}));
  demand(exact,"official SDK/native tick arithmetic mismatch or incomplete four-trial parity");
}
try{main()}catch(error){console.error("CLMM OFFICIAL SDK ORACLE FAILED",error.stack||String(error));process.exitCode=1}
