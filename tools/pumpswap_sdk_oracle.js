#!/usr/bin/env node
"use strict";
/** Independent PumpSwap SDK quote oracle over authenticated captured account bytes.
 *
 * The input is an untrusted research artifact. Pool and quote bytes are decoded
 * through the published SDK; a match does NOT constitute signed Surfpool parity.
 * No RPC, signing or broadcasting occurs in this process.
 */
const fs = require("fs");
const crypto = require("crypto");
const BN = require("bn.js");
const {
  PUMP_AMM_SDK, buyQuoteInput, sellBaseInput
} = require("@pump-fun/pump-swap-sdk");

function check(x, msg) { if (!x) throw new Error(msg); }
function raw(row) {
  check(row && typeof row.account_base64 === "string", "missing account bytes");
  const b=Buffer.from(row.account_base64,"base64");
  check(b.length > 0 && b.toString("base64") === row.account_base64, "invalid base64");
  return b;
}
function canonicalJson(value) {
  if (Array.isArray(value)) return "["+value.map(canonicalJson).join(",")+"]";
  if (value && typeof value==="object") {
    return "{"+Object.keys(value).sort().map(
      key=>JSON.stringify(key)+":"+canonicalJson(value[key])
    ).join(",")+"}";
  }
  return JSON.stringify(value);
}
function verifySourceDigest(snapshot, accounts) {
  check(typeof snapshot.authenticated_source_sha256==="string" &&
    /^[a-f0-9]{64}$/.test(snapshot.authenticated_source_sha256),
    "missing authenticated source digest");
  const payload={slot:snapshot.verified_snapshot_slot,accounts};
  const digest=crypto.createHash("sha256").update(canonicalJson(payload),"utf8").digest("hex");
  check(digest===snapshot.authenticated_source_sha256,
    "SOURCE_SNAPSHOT_INTEGRITY_MISMATCH");
}
function compare(snapshot) {
  check(snapshot.status === "AUTHENTICATED_SOURCE_ONLY", "unauthenticated source");
  const accounts=snapshot.authenticated_source_accounts;
  check(Array.isArray(accounts) && accounts.length === 6, "source account bundle missing");
  check(Number.isSafeInteger(snapshot.verified_snapshot_slot) && snapshot.verified_snapshot_slot >= 0,
    "invalid source slot");
  verifySourceDigest(snapshot,accounts);
  const [p,baseVault,quoteVault,globalAccount,feesAccount,mintAccount] = accounts;
  check(p.address === snapshot.address, "pool address mismatch");
  const pool=PUMP_AMM_SDK.decodePool({data:raw(p)});
  const globalConfig=PUMP_AMM_SDK.decodeGlobalConfig({data:raw(globalAccount)});
  const feeConfig=PUMP_AMM_SDK.decodeFeeConfig({data:raw(feesAccount)});
  const poolBase=String(pool.baseMint);
  const poolQuote=String(pool.quoteMint);
  check(snapshot.mints[0] === poolBase && snapshot.mints[1] === poolQuote, "pool mint identity mismatch");
  check(baseVault.address === String(pool.poolBaseTokenAccount), "base vault mismatch");
  check(quoteVault.address === String(pool.poolQuoteTokenAccount), "quote vault mismatch");
  const vault0=raw(baseVault),vault1=raw(quoteVault),mintRaw=raw(mintAccount);
  check(vault0.length >=72 && vault1.length >=72 && mintRaw.length>=44,
    "truncated source vault or mint");
  const baseReserve=new BN(vault0.readBigUInt64LE(64).toString());
  const quoteReserve=new BN(vault1.readBigUInt64LE(64).toString());
  const mintSupply=BigInt(mintRaw.readBigUInt64LE(36));
  const baseMintAccount={supply:mintSupply};
  const params={baseReserve,quoteReserve,virtualQuoteReserves:pool.virtualQuoteReserves,
    globalConfig,baseMintAccount,baseMint:pool.baseMint,coinCreator:pool.coinCreator,
    creator:pool.creator,feeConfig,quoteMint:pool.quoteMint,
    isMayhemMode:pool.isMayhemMode,creatorFeeBps:pool.creatorFeeBps,slippage:0,
    feeBucketsTotal:pool.protocolFees.add(pool.creatorFees)};
  const rows=[];
  const selections=snapshot.native_quote_candidates;
  check(Array.isArray(selections) && selections.length===4,"four native source candidate quotes required");
  const identities=new Set();
  for (const candidate of selections) {
    const input=candidate.mint_in;
    const amount=candidate.amount_in;
    check((input===poolBase || input===poolQuote) &&
      Number.isSafeInteger(amount) && amount>0,
      "invalid native source quote mint or size");
    const identity=input+":"+amount;
    check(!identities.has(identity),"duplicate native quote candidate");
    identities.add(identity);
    let result;
    try {
      check(!pool.isCashbackCoin, "cashback V2 unsupported");
      const inputBN=new BN(String(amount));
      const sdkQuote=input===poolBase
        ? sellBaseInput({...params,base:inputBN}).uiQuote
        : buyQuoteInput({...params,quote:inputBN}).base;
      const candidate=snapshot.native_quote_candidates.find(
        x=>x.mint_in===input && x.amount_in===amount);
      check(candidate,"missing candidate");
      check(candidate.status === "UNVERIFIED_NATIVE_FORMULA_CANDIDATE",
        "Python candidate blocked: "+(candidate.reason||"unknown"));
      check(Number.isSafeInteger(candidate.native_formula_candidate_out),
        "invalid Python candidate output");
      check(sdkQuote.eq(new BN(String(candidate.native_formula_candidate_out))),
        "OFFICIAL_SDK_PRICE_MISMATCH");
      result={direction:input===poolBase?"base_to_quote":"quote_to_base",
        input_mint:input,amount_in:amount,official_sdk_output:sdkQuote.toString(),
        python_candidate_output:String(candidate.native_formula_candidate_out),
        status:"OFFICIAL_SDK_CANDIDATE_EXACT",signed_parity_verified:false};
    } catch(error) {
      result={direction:input===poolBase?"base_to_quote":"quote_to_base",
        input_mint:input,amount_in:amount,status:"OFFICIAL_SDK_CANDIDATE_BLOCKED",
        reason:String(error.message).slice(0,240),signed_parity_verified:false};
    }
    rows.push(result);
  }
  return {address:snapshot.address,source_slot:snapshot.verified_snapshot_slot,
    source_digest:snapshot.authenticated_source_sha256,
    trials:rows,exact_candidates:rows.filter(x=>x.status==="OFFICIAL_SDK_CANDIDATE_EXACT").length,
    signed_parity_verified:false,actionable:false};
}
function main() {
  check(process.argv.length===4,"usage: node sdk_oracle.js source.json sdk-report.json");
  const report=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
  check(report.venue==="pumpswap" && Array.isArray(report.pools),"wrong source artifact");
  const pools=report.pools.map(row=>{
    try { return compare(row); }
    catch(error) {return {address:row.address,exact_candidates:0,
      status:"SDK_SOURCE_REJECTED",reason:String(error.message).slice(0,240),
      signed_parity_verified:false,actionable:false};}
  });
  const out={venue:"pumpswap",status:"INDEPENDENT_SDK_CANDIDATE_AUDIT",
    sdk_candidate_verified_pools:pools.filter(x=>x.exact_candidates===4).length,
    requested:report.requested,pools,actionable:false,broadcast:false,
    signed_parity_verified:false,registry_admission_approved:false};
  fs.writeFileSync(process.argv[3],JSON.stringify(out,null,2)+"\n");
  console.log(JSON.stringify({status:out.status,verified:out.sdk_candidate_verified_pools,
    requested:out.requested}));
  if(out.sdk_candidate_verified_pools!==out.requested) process.exitCode=1;
}
main();
