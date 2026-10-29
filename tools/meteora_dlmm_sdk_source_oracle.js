"use strict";
/** Fifth-venue independent official Meteora DLMM SDK source-state quote probe.
 * Read-only source RPC. No transactions are built, signed or sent.
 * Captured pool bytes must equal the SDK's pool state before and after
 * quoting: a quote from a drifting source is NOT native integer parity.
 */
const fs=require("fs");
const crypto=require("crypto");
const sdkModule=require("@meteora-ag/dlmm");
const DLMM=sdkModule.default || sdkModule.DLMM || sdkModule;
const BN=require("bn.js");
const {Connection,PublicKey}=require("@solana/web3.js");

function check(predicate,message) { if(!predicate) throw Error(message); }
function canonical(value) {
  if(Array.isArray(value)) return "["+value.map(canonical).join(",")+"]";
  if(value&&typeof value==="object")
    return "{"+Object.keys(value).sort().map(k=>JSON.stringify(k)+":"+canonical(value[k])).join(",")+"}";
  return JSON.stringify(value);
}
function hash(records,slot) {
  return crypto.createHash("sha256").update(canonical({slot,accounts:records})).digest("hex");
}
function flatAccount(row,address) {
  return row.source_accounts.find(a=>a.address===address && typeof a.account_base64==="string");
}
/** Pin every captured account to the exact authenticated same-slot snapshot.
 * Active DLMM pools change multiple times per second. Asking the official SDK
 * to reread live pool bytes would compare different states, not independent
 * implementations of the SAME state. All pool/bin/Clock bytes returned here
 * remain identical to the authenticated RPC capture and SHA-256 digest.
 */
function snapshotConnection(remote,row) {
  const snapshot=new Map();
  for(const account of row.source_accounts) {
    if(account.present===false) continue;
    const raw=Buffer.from(account.account_base64,"base64");
    check(raw.toString("base64")===account.account_base64,
      "noncanonical authenticated DLMM snapshot account");
    snapshot.set(account.address,{
      data:raw,owner:new PublicKey(account.owner),
      executable:false,lamports:account.lamports,rentEpoch:0
    });
  }
  check(snapshot.has(row.address),"authenticated DLMM pool account missing");
  const conn=new Connection(remote.rpcEndpoint,{commitment:"confirmed"});
  const originalGetInfo=conn.getAccountInfo.bind(conn);
  const originalGetInfoContext=conn.getAccountInfoAndContext.bind(conn);
  const originalMulti=conn.getMultipleAccountsInfo.bind(conn);
  conn.getAccountInfo=async(key,...args)=>{
    const cached=snapshot.get(key.toBase58());
    return cached || originalGetInfo(key,...args);
  };
  conn.getAccountInfoAndContext=async(key,...args)=>{
    const cached=snapshot.get(key.toBase58());
    return cached ? {context:{slot:row.source_slot},value:cached} :
      originalGetInfoContext(key,...args);
  };
  conn.getMultipleAccountsInfo=async(keys,...args)=>{
    // SDK calls this with ordered bin-array paths. Any off-snapshot arrays
    // must fail below rather than produce mixed-state parity evidence.
    const cached=keys.map(key=>snapshot.get(key.toBase58()));
    if(cached.every(Boolean)) return cached;
    const remoteRows=await originalMulti(keys,...args);
    return keys.map((key,i)=>cached[i] || remoteRows[i]);
  };
  return conn;
}
async function checkPool(conn,row,publicKey) {
  const now=await conn.getAccountInfo(publicKey,"confirmed");
  const original=flatAccount(row,row.address);
  check(original&&now&&now.owner.toBase58()==="LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo",
    "DLMM source pool account owner mismatch");
  check(now.data.toString("base64")===original.account_base64,
    "DLMM source pool changed during SDK read");
}
async function probe(conn,row) {
  check(row.status==="AUTHENTICATED_BIN_SNAPSHOT_ONLY"&&
    row.signed_parity_verified===false&&row.native_pricing_verified===false,
    "authenticated unsigned DLMM source required");
  check(Array.isArray(row.source_accounts)&&row.source_accounts.length===10,
    "complete DLMM pool-vault-oracle-bin-mint snapshot required");
  check(hash(row.source_accounts,row.source_slot)===row.source_sha256,
    "DLMM source snapshot SHA-256 integrity mismatch");
  const address=new PublicKey(row.address);
  const pinned=snapshotConnection(conn,row);
  await checkPool(pinned,row,address);
  const pair=await DLMM.create(pinned,address,{cluster:"mainnet-beta"});
  await checkPool(pinned,row,address);
  const trials=[];
  for(const swapForY of [true,false]) {
    // Small and larger base-unit amounts, exact-in and nonpartial. These are
    // research source quotes; signability must be proved later on Surfpool.
    const arrays=await pair.getBinArrayForSwap(swapForY,3);
    check(Array.isArray(arrays)&&arrays.length>0,
      "official SDK did not identify bin array path");
    const pinnedBins=new Set(row.bin_arrays.filter(b=>b.authenticated).map(b=>b.pda));
    check(arrays.every(a=>pinnedBins.has(a.publicKey.toBase58())),
      "SDK requested a bin array outside authenticated source snapshot");
    for(const amount of [10000,100000]) {
      const quoted=await pair.swapQuote(
        new BN(amount),swapForY,new BN(0),arrays,false);
      const consumed=quoted.consumedInAmount;
      const output=quoted.outAmount;
      check(consumed && output && consumed.toString()==String(amount)
          && output.gt(new BN(0)),"DLMM exact-input SDK quote partial or zero");
      trials.push({
        input_mint:row.mints[swapForY?0:1],
        output_mint:row.mints[swapForY?1:0],
        swap_for_y:swapForY,amount_in:amount,
        official_sdk_output:output.toString(),
        consumed_input:consumed.toString(),
        fee:quoted.fee.toString(),
        protocol_fee:quoted.protocolFee.toString(),
        bin_array_path:quoted.binArraysPubkey.map(p=>p.toBase58()),
        status:"OFFICIAL_DLMM_SDK_SOURCE_QUOTE_ONLY",
        signed_parity_verified:false
      });
    }
    await checkPool(conn,row,address);
  }
  await checkPool(conn,row,address);
  return {pool:row.address,source_slot:row.source_slot,
    source_sha256:row.source_sha256,trials,
    signed_parity_verified:false,actionable:false};
}
async function main() {
  check(process.argv.length===5,
    "usage node tools/meteora_dlmm_sdk_source_oracle.js SOURCE.json REPORT.json RPC_URL");
  const source=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));
  check(source.venue==="meteora_dlmm"&&Array.isArray(source.pools)
      &&source.pools.length>=1&&source.authenticated===source.pools.length,
      "invalid fifth-venue source report");
  const rpc=process.argv[4];
  check(/^https:\/\//.test(rpc)||/^http:\/\/127\.0\.0\.1:/.test(rpc),
    "DLMM SDK must use read-only HTTPS source or isolated localhost RPC");
  const conn=new Connection(rpc,{commitment:"confirmed"});
  const results=[];
  for(const row of source.pools) results.push(await probe(conn,row));
  const output={venue:"meteora_dlmm",status:"DLMM_SDK_SOURCE_QUOTES_NOT_NATIVE_PARITY",
    official_sdk_candidate_pools:results.length,pools:results,
    signed_parity_verified:false,native_pricing_verified:false,
    registry_admission_approved:false,actionable:false,broadcast:false};
  fs.writeFileSync(process.argv[3],JSON.stringify(output,null,2)+"\n");
  console.log(JSON.stringify({status:output.status,pools:results.length}));
}
main().catch(error=>{console.error("DLMM SDK SOURCE QUOTE FAILED:",error.stack||String(error));process.exit(1)});
