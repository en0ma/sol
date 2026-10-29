"use strict";
/** Original DBC exact authenticated byte snapshot -> OFFICIAL SDK quote oracle.
 * No mainnet RPC and no transaction signing. Native parity and signed
 * acceptance are deliberately absent until independently demonstrated.
 * npm: @meteora-ag/dynamic-bonding-curve-sdk@2.0.0
 */
const fs=require("fs");
const crypto=require("crypto");
const BN=require("bn.js");
const {Connection}=require("@solana/web3.js");
const {DynamicBondingCurveClient}=require("@meteora-ag/dynamic-bonding-curve-sdk");

function requireTrue(ok,message) { if(!ok) throw Error(message); }
function bytes(row) {
  requireTrue(row&&typeof row.account_base64==="string" &&
    typeof row.sha256==="string","DBC authenticated source account missing");
  const raw=Buffer.from(row.account_base64,"base64");
  requireTrue(raw.toString("base64")===row.account_base64,
    "DBC authenticated source encoding noncanonical");
  const digest=crypto.createHash("sha256").update(raw).digest("hex");
  requireTrue(digest===row.sha256,"DBC authenticated source digest disagreement");
  return raw;
}
const [,,sourcePath,outputPath]=process.argv;
requireTrue(sourcePath&&outputPath,"usage: node oracle.js source.json output.json");
const report=JSON.parse(fs.readFileSync(sourcePath,"utf8"));
requireTrue(report.status==="DBC_ORIGINAL_CONTEXTUAL_SOURCE_PARTIAL_NOT_SIGNED" &&
  Array.isArray(report.source_pools) && report.source_pools.length>0,
  "DBC original source proof required");
const client=new DynamicBondingCurveClient(
  new Connection("http://127.0.0.1:8899","confirmed"),"confirmed"
);
const coder=client.program.coder.accounts;
const results=[];
for(const row of report.source_pools) {
  requireTrue(row.status==="DBC_CONTEXTUAL_POOL_DEPENDENCIES_PARTIALLY_VERIFIED" &&
    row.pricing_eligible===false && row.signed_parity_verified===false,
    "DBC source status must remain conservative");
  const roles=row.pool_fields;
  const rawPool=bytes(row.accounts[row.pool]);
  const rawConfig=bytes(row.accounts[roles.config]);
  const rawClock=bytes(row.accounts["SysvarC1ock11111111111111111111111111111111"]);
  requireTrue(rawClock.length===40,"DBC Clock original source invalid");
  const virtualPool=coder.decode("virtualPool",rawPool);
  const config=coder.decode("poolConfig",rawConfig);
  requireTrue(virtualPool.poolState.config.toBase58()===roles.config &&
    virtualPool.poolState.baseMint.toBase58()===roles.base_mint &&
    config.quoteMint.toBase58()===roles.quote_mint,
    "DBC SDK decoded roles disagree with original source");
  requireTrue(virtualPool.poolState.isMigrated===0 &&
    virtualPool.poolState.poolType===0 && 
    virtualPool.poolState.migrationProgress===0,
    "DBC unsupported migrated or token2022 pool");
  const activationType=config.activationType;
  requireTrue(activationType===0 || activationType===1,
    "DBC unsupported activation clock kind");
  const currentPoint=new BN(
    String(activationType===0 ? row.clock_slot : row.clock_unix_timestamp)
  );
  requireTrue(currentPoint.gt(new BN(0)),"DBC missing authenticated Clock point");
  const trials=[];
  for(const swapBaseForQuote of [true,false]) {
    for(const amount of ["10000","100000"]) {
      const input=new BN(amount);
      // Original SDK's fee engine and curve walk are deliberately the oracle.
      const quote=client.pool.swapQuote({
        virtualPool, config, swapBaseForQuote,
        amountIn:input, slippageBps:0, hasReferral:false,
        currentPoint, eligibleForFirstSwapWithMinFee:false
      });
      requireTrue(quote.outputAmount.gt(new BN(0)) &&
        quote.actualInputAmount.gte(new BN(0)),
        "DBC SDK quote cannot qualify zero or negative output");
      trials.push({
        direction:swapBaseForQuote?"base_to_quote":"quote_to_base",
        amount_in:amount, sdk_output:quote.outputAmount.toString(10),
        sdk_actual_input:quote.actualInputAmount.toString(10),
        sdk_next_sqrt_price:quote.nextSqrtPrice.toString(10),
        sdk_protocol_fee:quote.protocolFee.toString(10),
        sdk_trading_fee:quote.tradingFee.toString(10)
      });
    }
  }
  results.push({
    pool:row.pool,source_slot:row.source_slot,
    source_pool_sha256:row.accounts[row.pool].sha256,
    source_config_sha256:row.accounts[roles.config].sha256,
    clock_sha256:row.accounts["SysvarC1ock11111111111111111111111111111111"].sha256,
    original_sdk_version:"@meteora-ag/dynamic-bonding-curve-sdk@2.0.0",
    clock_point:currentPoint.toString(10),trials,
    native_pricing_verified:false,signed_verified:false
  });
}
fs.writeFileSync(outputPath,JSON.stringify({
  status:"DBC_ORIGINAL_OFFICIAL_SDK_QUOTES_ONLY_NOT_NATIVE_PARITY",
  pools:results,native_pricing_verified:false,signed_verified:false,
  actionable:false,broadcast:false
},null,2)+"\n");
console.log(JSON.stringify({sdk_quoted_pools:results.length,signed_verified:false}));
