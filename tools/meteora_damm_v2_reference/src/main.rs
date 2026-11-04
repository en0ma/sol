//! Exact Meteora DAMM v2 reference: published Rust SDK + published on-chain Pool.
use base64::{engine::general_purpose::STANDARD, Engine};
use cp_amm::state::Pool;
use rust_sdk::quote_exact_in::get_quote;
use serde_json::{json,Value};
use std::{io::{self,Read},process};
fn get<'a>(v:&'a Value,k:&str)->Result<&'a Value,String>{
    v.get(k).ok_or_else(||format!("missing {}",k))
}
fn unsigned(v:&Value)->Result<u64,String>{
    if let Some(s)=v.as_str(){return s.parse::<u64>().map_err(|e|e.to_string());}
    v.as_u64().ok_or_else(||"invalid u64".to_string())
}
fn quote(root:Value)->Result<Value,String>{
    let raw=STANDARD.decode(get(&root,"pool_data_base64")?.as_str()
        .ok_or("missing base64 pool bytes")?).map_err(|e|e.to_string())?;
    if raw.len()!=1112 || &raw[..8]!=&[241,154,109,4,17,177,109,188]{
        return Err("invalid captured Meteora Pool account length/discriminator".into());
    }
    let pool:Pool=bytemuck::pod_read_unaligned(&raw[8..]);
    let input=unsigned(get(&root,"amount_in")?)?;
    let timestamp=unsigned(get(&root,"fork_unix_timestamp")?)?;
    let slot=unsigned(get(&root,"fork_clock_slot")?)?;
    let a_to_b=get(&root,"input_is_a")?.as_bool().ok_or("direction must be boolean")?;
    if input==0 || timestamp==0 || slot==0{return Err("signed amount/Clock missing".into());}
    let result=get_quote(&pool,timestamp,slot,input,a_to_b,false)
        .map_err(|e|format!("official Meteora quote rejected pool: {e}"))?;
    Ok(json!({"status":"OFFICIAL_METEORA_DAMM_V2_EXACT_INPUT",
        "amount_in":input,"amount_out":result.output_amount,
        "amount_left":result.amount_left,"included_fee_input_amount":result.included_fee_input_amount,
        "excluded_fee_input_amount":result.excluded_fee_input_amount,
        "claiming_fee":result.claiming_fee,"compounding_fee":result.compounding_fee,
        "protocol_fee":result.protocol_fee,
        "next_sqrt_price":result.next_sqrt_price.to_string(),
        "official_repository_revision":"5398b5c7c534de014091132da37c6478cce671a8",
        "actionable":false,"broadcast":false,"live_execution_approved":false}))
}
fn main(){
    let mut input=String::new();
    if let Err(e)=io::stdin().read_to_string(&mut input){eprintln!("{e}");process::exit(2)}
    match serde_json::from_str::<Value>(&input).map_err(|e|e.to_string()).and_then(quote){
        Ok(result)=>println!("{result}"),
        Err(e)=>{eprintln!("official Meteora quote blocked: {e}");process::exit(1)}
    }
}
