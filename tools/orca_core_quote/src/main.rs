//! Run Orca's published integer quote engine on authenticated fork account data.
//! No network activity, keys, transaction creation, RPC, or custom quote math.
use orca_whirlpools_core::{
    swap_quote_by_input_token, AdaptiveFeeConstantsFacade, AdaptiveFeeVariablesFacade,
    OracleFacade, TickArrayFacade, TickArrays, TickFacade, WhirlpoolFacade,
    TICK_ARRAY_SIZE,
};
use serde_json::{json, Value};
use std::{io::{self, Read}, process};

fn value<'a>(object: &'a Value, key: &str) -> Result<&'a Value, String> {
    object.get(key).ok_or_else(|| format!("missing {}", key))
}
fn num(v: &Value) -> Result<u64, String> {
    if let Some(s) = v.as_str() { return s.parse::<u64>().map_err(|e| format!("u64: {}",e)); }
    v.as_u64().ok_or_else(|| "expected positive integer or unsigned decimal string".to_string())
}
fn signed(v: &Value) -> Result<i64, String> {
    if let Some(s) = v.as_str() { return s.parse::<i64>().map_err(|e| format!("i64: {}",e)); }
    v.as_i64().ok_or_else(|| "expected signed integer or decimal string".to_string())
}
fn unsigned128(v: &Value) -> Result<u128, String> {
    if let Some(s) = v.as_str() { return s.parse::<u128>().map_err(|e| format!("u128: {}",e)); }
    Ok(num(v)? as u128)
}
fn signed128(v: &Value) -> Result<i128, String> {
    if let Some(s) = v.as_str() { return s.parse::<i128>().map_err(|e| format!("i128: {}",e)); }
    Ok(signed(v)? as i128)
}
fn at(v: &Value, k: &str) -> Result<u64, String> { num(value(v,k)?) }
fn small(v: &Value,k:&str)->Result<u16,String>{u16::try_from(at(v,k)?).map_err(|_|format!("{} out of u16 range",k))}
fn wide(v:&Value,k:&str)->Result<u32,String>{u32::try_from(at(v,k)?).map_err(|_|format!("{} out of u32 range",k))}
fn integer(v:&Value,k:&str)->Result<i32,String>{i32::try_from(signed(value(v,k)?)?).map_err(|_|format!("{} out of i32 range",k))}
fn from_json(root: Value) -> Result<Value, String> {
    let pool=value(&root,"pool")?;
    let fee_tier=small(pool,"fee_tier_index_seed")?;
    let spacing=small(pool,"tick_spacing")?;
    let base_fee=small(pool,"fee_rate_hundredths_bps")?;
    let price=unsigned128(value(pool,"sqrt_price_x64")?)?;
    let liquidity=unsigned128(value(pool,"liquidity")?)?;
    if spacing==0 || price==0 || liquidity==0 { return Err("pool price/liquidity/spacing invalid".to_string()); }
    let whirlpool=WhirlpoolFacade {
        fee_tier_index_seed:fee_tier.to_le_bytes(),
        tick_spacing:spacing,
        fee_rate:base_fee,
        protocol_fee_rate:small(pool,"protocol_fee_rate").unwrap_or(0),
        liquidity,
        sqrt_price:price,
        tick_current_index:integer(pool,"tick_current_index")?,
        ..WhirlpoolFacade::default()
    };
    let oracle=match root.get("oracle") {
        Some(o) if !o.is_null() => {
            let c=value(o,"constants")?;
            let v=value(o,"variables")?;
            Some(OracleFacade {
                trade_enable_timestamp:at(o,"trade_enable_timestamp")?,
                adaptive_fee_constants:AdaptiveFeeConstantsFacade{
                    filter_period:small(c,"filter_period")?,
                    decay_period:small(c,"decay_period")?,
                    reduction_factor:small(c,"reduction_factor")?,
                    adaptive_fee_control_factor:wide(c,"adaptive_fee_control_factor")?,
                    max_volatility_accumulator:wide(c,"max_volatility_accumulator")?,
                    tick_group_size:small(c,"tick_group_size")?,
                    major_swap_threshold_ticks:small(c,"major_swap_threshold_ticks")?,
                },
                adaptive_fee_variables:AdaptiveFeeVariablesFacade{
                    last_reference_update_timestamp:at(v,"last_reference_update_timestamp")?,
                    last_major_swap_timestamp:at(v,"last_major_swap_timestamp")?,
                    volatility_reference:wide(v,"volatility_reference")?,
                    tick_group_index_reference:integer(v,"tick_group_index_reference")?,
                    volatility_accumulator:wide(v,"volatility_accumulator")?,
                },
            })
        }
        _=>None,
    };
    if (fee_tier!=spacing)!=oracle.is_some() {
        return Err("adaptive Orca fee tier must have Oracle; static must not invent one".to_string());
    }
    let array_values=value(&root,"arrays")?.as_array().ok_or("arrays must be a list")?;
    if array_values.is_empty() || array_values.len()>6 {
        return Err("Orca Core requires 1..6 authenticated directional tick arrays".to_string());
    }
    let mut arrays=Vec::new();
    for a in array_values {
        let start=integer(a,"start_tick")?;
        let mut ticks=[TickFacade::default();TICK_ARRAY_SIZE];
        let records=value(a,"ticks")?.as_array().ok_or("ticks must be a list")?;
        for t in records {
            let index=integer(t,"tick_index")?;
            let delta=index-start;
            if delta<0 || delta%spacing as i32!=0 || (delta/spacing as i32) as usize>=TICK_ARRAY_SIZE {
                return Err("source tick not in the declared array".to_string());
            }
            let pos=(delta/spacing as i32) as usize;
            if ticks[pos].initialized { return Err("duplicate initialized tick".to_string()); }
            ticks[pos]=TickFacade{
                initialized:true,
                liquidity_net:signed128(value(t,"liquidity_net")?)?,
                liquidity_gross:unsigned128(value(t,"liquidity_gross")?)?,
                ..TickFacade::default()
            };
        }
        arrays.push(TickArrayFacade{start_tick_index:start,ticks});
    }
    let ticks=match arrays.as_slice(){
        [a]=>TickArrays::One(*a),
        [a,b]=>TickArrays::Two(*a,*b),
        [a,b,c]=>TickArrays::Three(*a,*b,*c),
        [a,b,c,d]=>TickArrays::Four(*a,*b,*c,*d),
        [a,b,c,d,e]=>TickArrays::Five(*a,*b,*c,*d,*e),
        [a,b,c,d,e,f]=>TickArrays::Six(*a,*b,*c,*d,*e,*f),
        _=>return Err("invalid directional source arrays".to_string())
    };
    let amount=at(&root,"amount_in")?;
    let timestamp=at(&root,"fork_unix_timestamp")?;
    let input_a=value(&root,"specified_token_a")?.as_bool().ok_or("specified_token_a must be boolean")?;
    if amount==0 || timestamp==0 {return Err("positive source input and actual Clock required".to_string());}
    let quote=swap_quote_by_input_token(amount,input_a,0,whirlpool,oracle,ticks,timestamp,None,None)
        .map_err(|e|format!("Orca Core refused swap quote: {:?}",e))?;
    Ok(json!({"status":"OFFICIAL_ORCA_CORE_EXACT_INPUT_QUOTE",
             "amount_in":amount,"amount_out":quote.token_est_out,
             "trade_fee":quote.trade_fee,
             "trade_fee_rate_min":quote.trade_fee_rate_min,
             "trade_fee_rate_max":quote.trade_fee_rate_max,
             "fork_unix_timestamp":timestamp,
             "official_library":"orca_whirlpools_core",
             "official_library_version":"2.1.1",
             "actionable":false,"broadcast":false,"live_execution_approved":false}))
}
fn main() {
    let mut input=String::new();
    if let Err(e)=io::stdin().read_to_string(&mut input) {
        eprintln!("stdin: {}",e);process::exit(2);
    }
    let result=serde_json::from_str::<Value>(&input)
        .map_err(|e|format!("invalid JSON: {}",e))
        .and_then(from_json);
    match result {
        Ok(output)=>println!("{}",output),
        Err(e)=>{eprintln!("Orca official quote blocked: {}",e);process::exit(1)}
    }
}
