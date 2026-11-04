"use strict";
/** Screen real source pools with the *official* Raydium SDK then emit only
 * six distinct exact native-SDK parity candidates. Every accepted account
 * retains its full independent cryptographic source proof, and all rejected
 * pools are recorded without signed/registry admission. */
const fs=require("fs");
const {quotePool}=require("./raydium_clmm_official_sdk_oracle");
function check(condition,message){if(!condition)throw Error(message)}
function main(){
 check(process.argv.length===8,
   "usage: node SCREEN.js TICKS NATIVE SDKOUT TICKSOUT NATIVEOUT REJECTIONSOUT");
 const tick=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
 const native=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));
 check(tick.venue==="raydium_clmm"&&
   tick.status==="AUTHENTICATED_TICK_LIQUIDITY_SOURCE_ONLY"&&
   native.status==="CLMM_SINGLE_TICK_NATIVE_CANDIDATES_NOT_SDK_VERIFIED",
   "six-pool official SDK screening requires authenticated source/native");
 const expected=new Map(native.pools.map(r=>[r.pool,r]));
 check(expected.size===native.pools.length,"duplicate source/native pool");
 const accepted=[],rejected=[];
 for(const row of tick.pools){
   const nativeRow=expected.get(row.pool);
   try{
     check(nativeRow&&nativeRow.quotes.length===4&&!nativeRow.blocked.length,
       "four native single-tick candidates incomplete");
     const result=quotePool(row,nativeRow);
     const verifiedArrays=new Set(row.tick_capture.tick_arrays
       .filter(a=>a.present===true).map(a=>a.address));
     check(result.trials.every(t=>
       Array.isArray(t.remaining_tick_arrays) &&
       t.remaining_tick_arrays.length>=1 &&
       t.remaining_tick_arrays.length<=5 &&
       new Set(t.remaining_tick_arrays).size===t.remaining_tick_arrays.length &&
       t.remaining_tick_arrays.every(a=>verifiedArrays.has(a))),
       "official SDK tick path not in original authenticated tick snapshot");
     check(result.trials.length===4&&result.matched===4,
       "four exact official SDK/native integer prices not achieved");
     check(result.trials.every(r=>r.all_trade===true &&
       r.official_fee===String(r.expected_fee_native)),
       "official SDK partial fill or fee disagreement");
     accepted.push({tick:row,native:nativeRow,sdk:result});
   }catch(e){
     rejected.push({pool:row.pool,reason:String(e.message||e).slice(0,280)});
   }
   if(accepted.length===6)break;
 }
 const choice=accepted.slice(0,6);
 const sdk={venue:"raydium_clmm",
   status:choice.length===6?"RAYDIUM_CLMM_NATIVE_SDK_SINGLE_TICK_EXACT":
      "RAYDIUM_CLMM_SIX_EXACT_SDK_POOLS_NOT_YET_FOUND",
   official_sdk_native_parity_verified:choice.length===6,
   signed_parity_verified:false,registry_admission_approved:false,
   actionable:false,broadcast:false,pools:choice.map(r=>r.sdk)};
 const tickOutput={...tick,pools:choice.map(r=>r.tick),rejected};
 const nativeOutput={...native,pools:choice.map(r=>r.native)};
 fs.writeFileSync(process.argv[4],JSON.stringify(sdk,null,2)+"\n");
 fs.writeFileSync(process.argv[5],JSON.stringify(tickOutput,null,2)+"\n");
 fs.writeFileSync(process.argv[6],JSON.stringify(nativeOutput,null,2)+"\n");
 fs.writeFileSync(process.argv[7],JSON.stringify({rejected,
   examined:choice.length+rejected.length,accepted:choice.length},null,2)+"\n");
 console.log(JSON.stringify({accepted:choice.length,rejected:rejected.length,
   signed_parity_verified:false}));
 check(choice.length===6,"six exact official SDK/native authenticated CLMM pools not found");
}
try{main()}catch(e){console.error("CLMM SIX SCREEN FAILED",e.stack||String(e));process.exitCode=1}
