"""Decode genuine Meteora DLMM BinArray liquidity, fail closed on layout.

Layout: discriminator(8), index(i64), version(u8), padding(7),
LB pair(32), 70 fixed Borsh Bin entries (144 bytes each).
Source: Meteora DLMM Codama BinArray/Bin definitions, account LEN 10136.
This is account-backed bin inventory only; no effective fee/executable quote.
"""
import base64
from arb.meteora_dlmm_bin_preflight import (
    BIN_ARRAY_DISC,BIN_ARRAY_SIZE,bin_array_pda
)
from arb.meteora_dlmm import PROGRAM
from arb.orca_whirlpool import b58

BIN_START=56
BIN_SIZE=144
EXPECTED_SIZE=BIN_START+BIN_ARRAY_SIZE*BIN_SIZE
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def decode_bin_array(raw, *, pool, index):
    if type(raw) is not bytes or len(raw)!=EXPECTED_SIZE:
        raise ValueError("DLMM BinArray source bytes not the canonical 10136-byte layout")
    if raw[:8]!=BIN_ARRAY_DISC:
        raise ValueError("DLMM BinArray discriminator mismatch")
    actual=int.from_bytes(raw[8:16],"little",signed=True)
    if type(index)is not int or actual!=index:
        raise ValueError("DLMM BinArray index mismatch")
    if raw[16] not in (0,1,2):
        raise ValueError("unsupported DLMM BinArray version")
    if b58(raw[24:56])!=pool:
        raise ValueError("DLMM BinArray parent pool mismatch")
    bins=[]
    for i in range(BIN_ARRAY_SIZE):
        offset=BIN_START+i*BIN_SIZE
        def number(start,n):
            return int.from_bytes(raw[offset+start:offset+start+n],"little")
        amount_x=number(0,8)
        amount_y=number(8,8)
        price=number(16,16)
        # The remaining 112 bytes encode liquidity supply, rewards,
        # fee-per-token checkpoints, and volume counters. Their values
        # do not modify current spendable bin token amounts.
        liquidity_supply=number(32,16)
        if (amount_x or amount_y) and (price==0 or liquidity_supply==0):
            raise ValueError("DLMM funded bin has zero price or liquidity supply")
        bins.append({"bin_id":index*BIN_ARRAY_SIZE+i,
                     "amount_x":amount_x,"amount_y":amount_y,
                     "price_q64":price,
                     "liquidity_supply":liquidity_supply,
                     "open_order_amount":number(112,8),
                     "processed_order_remaining_amount":number(128,8),
                     "limit_order_ask_side":number(140,1)})
    return {"pool":pool,"array_index":index,"array_version":raw[16],
            "bin_count":BIN_ARRAY_SIZE,"bins":bins,
            "active_bin_fee_verified":False,"protocol_exact_verified":False,**SAFE}

def decode_from_fixture(fixture, *, pool, array_index):
    from arb.source_snapshot_manifest import verify
    verify(fixture)
    if any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("unsafe DLMM source fixture")
    pda=bin_array_pda(pool,array_index)
    if pda not in fixture["state_account_addresses"]:
        raise ValueError("canonical DLMM BinArray missing from single-slot state inventory")
    account=fixture["accounts"][pda]
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("DLMM BinArray owner mismatch")
    encoded=account.get("data")
    if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
        raise ValueError("DLMM BinArray base64 source unavailable")
    raw=base64.b64decode(encoded[0],validate=True)
    result=decode_bin_array(raw,pool=pool,index=array_index)
    return {**result,"source_slot":fixture["state_accounts_observed_slot"],
            "bin_array_pda":pda,"source_account_verified":True,**SAFE}

def directional_bins(decoded_arrays, *, active_id, x_to_y, maximum_bins=70):
    if (type(active_id)is not int or type(x_to_y)is not bool
            or type(maximum_bins)is not int or not 1<=maximum_bins<=210):
        raise ValueError("invalid DLMM active bin direction")
    all_bins={}
    for decoded in decoded_arrays:
        if not isinstance(decoded,dict) or decoded.get("source_account_verified") is not True:
            raise ValueError("source-authenticated DLMM arrays required")
        for b in decoded["bins"]:
            if b["bin_id"] in all_bins:
                raise ValueError("overlapping DLMM bin arrays")
            all_bins[b["bin_id"]]=b
    direction=-1 if x_to_y else 1
    selected=[]
    current=active_id
    while current in all_bins and len(selected)<maximum_bins:
        b=all_bins[current]
        selected.append({**{k:b[k] for k in ("bin_id","amount_x","amount_y","price_q64")},
            **{k:b[k] for k in ("open_order_amount","processed_order_remaining_amount","limit_order_ask_side") if k in b}})
        current+=direction
    return {"bins":selected,"dynamic_fee_verified":False,
            "protocol_exact_verified":False,**SAFE}


# Official SDK LbPair::bitmap_range, BinArrayBitmapExtension::bit and
# shift_active_bin_if_empty_gap. Internal bitmap begins after the oracle key.
def bitmap_initialized(raw,index,*,extension_raw=None):
    from arb.meteora_dlmm import DISC,SIZE
    if type(raw) is not bytes or len(raw)!=SIZE or raw[:8]!=DISC or type(index) is not int:
        raise ValueError("invalid DLMM pool bitmap input")
    if -512<=index<512:
        return bool((int.from_bytes(raw[584:712],"little")>>(index+512))&1)
    if not -6656<=index<6656 or extension_raw is None:
        return None
    from arb.meteora_dlmm_bin_preflight import BITMAP_EXTENSION_DISC,BITMAP_EXTENSION_SIZE
    if (type(extension_raw) is not bytes or len(extension_raw)!=BITMAP_EXTENSION_SIZE
            or extension_raw[:8]!=BITMAP_EXTENSION_DISC):
        raise ValueError("invalid DLMM extension bitmap bytes")
    bit=index-512 if index>=512 else -index-513
    offset=40 if index>=512 else 808
    return bool((int.from_bytes(extension_raw[offset:offset+768],"little")>>bit)&1)


def bitmap_directional_bins(fixture,*,pool,active_id,x_to_y,proof,maximum_arrays=8):
    """Walk only source-captured initialized arrays with proven empty gaps.

    At most eight source window positions, never synthesize bins or skip a
    missing set bit. An unavailable external bitmap ends the coverage.
    Existing contiguous fixtures remain supported by directional_bins.
    """
    from arb.source_snapshot_manifest import verify
    from arb.meteora_dlmm_bin_preflight import (active_bin_array_index,
        verify_directional_bin_snapshot,verified_bitmap_extension_address)
    verify(fixture)
    if (any(fixture.get(k) is not False for k in SAFE)
            or pool not in fixture["state_account_addresses"]
            or type(x_to_y) is not bool or type(maximum_arrays) is not int
            or not 1<=maximum_arrays<=8 or not isinstance(proof,dict)
            or proof.get("bitmap_extension_source") is None):
        raise ValueError("bound DLMM bitmap directional fixture required")
    source=proof.get("directional_bin_source")
    center=active_bin_array_index(active_id)
    if (not isinstance(source,dict) or source.get("active_bin_array_index")!=center
            or source.get("input_is_x") is not x_to_y):
        raise ValueError("DLMM bitmap source direction mismatch")
    accounts=fixture["accounts"]
    verify_directional_bin_snapshot(pool,source,accounts)
    extension=verified_bitmap_extension_address(pool,proof,fixture)
    account=accounts[pool]
    if account.get("owner")!=PROGRAM or account.get("executable") is not False:
        raise ValueError("DLMM source bitmap pool owner mismatch")
    raw=base64.b64decode(account["data"][0],validate=True)
    from arb.meteora_dlmm import decode
    if decode(raw)["active_id"]!=active_id:
        raise ValueError("DLMM source bitmap active bin mismatch")
    ext_raw=base64.b64decode(accounts[extension]["data"][0],validate=True) if extension else None
    step=-1 if x_to_y else 1
    bins=[];arrays=[];skipped=[];missing=[]
    stop="CAPTURED_DIRECTIONAL_WINDOW_LIMIT"
    for observation in source["observations"][:maximum_arrays]:
        index=observation["index"]
        address=observation["address"]
        initialized=bitmap_initialized(raw,index,extension_raw=ext_raw)
        if initialized is None:
            stop="UNAVAILABLE_BITMAP_COVERAGE"
            missing.append({"array_index":index,"reason":stop})
            break
        if not initialized:
            if address in accounts:
                decoded=decode_from_fixture(fixture,pool=pool,array_index=index)
                if any(b["amount_x"] or b["amount_y"] or b["open_order_amount"]
                       or b["processed_order_remaining_amount"] for b in decoded["bins"]):
                    raise ValueError("DLMM clear bitmap conflicts with captured funded bin array")
            if index==center:
                # The existing fee schedule starts at the authenticated
                # active bin. Do not extrapolate initial empty-array shifts.
                stop="ACTIVE_ARRAY_BITMAP_CLEAR"
                missing.append({"array_index":index,"reason":stop})
                break
            skipped.append(index)
            continue
        if address not in fixture["state_account_addresses"]:
            stop="INITIALIZED_ARRAY_NOT_CAPTURED"
            missing.append({"array_index":index,"reason":stop})
            break
        decoded=decode_from_fixture(fixture,pool=pool,array_index=index)
        arrays.append(decoded)
        ordered=decoded["bins"][::-1] if x_to_y else decoded["bins"]
        for b in ordered:
            if (b["bin_id"]-active_id)*step<0:
                continue
            bins.append({k:b[k] for k in ("bin_id","amount_x","amount_y","price_q64",
                "open_order_amount","processed_order_remaining_amount","limit_order_ask_side")})
    return {"bins":bins,"arrays":arrays,"missing_arrays":missing,
            "verified_empty_arrays":skipped,"coverage_status":stop,
            "source_slot":fixture["state_accounts_observed_slot"],"source_bitmap_verified":True,
            "protocol_exact_verified":False,**SAFE}


def bounded_active_bin_input_candidates(bin_record,*,amount_in,x_to_y,fee_on_input,limit_order_support):
    """Pick smaller controls strictly inside one genuine funded MM bin.

    Zero-fee sizing limits output capacity; the existing native bin engine
    checks complete fills at both zero and maximum fee. This is not an
    assertion of effective fee or executable liquidity.
    """
    from arb.meteora_dlmm_bin_quote import quote_bins
    from arb.meteora_dlmm_source_fee_decoder import MAX_FEE_NUMERATOR
    if (type(amount_in) is not int or not 0<amount_in<2**64 or type(x_to_y) is not bool
            or type(fee_on_input) is not bool or type(limit_order_support) is not bool):
        raise ValueError("invalid active-bin research size input")
    capacity=bin_record["amount_y" if x_to_y else "amount_x"]
    price=bin_record["price_q64"]
    if type(capacity) is not int or not 0<=capacity<2**64 or type(price) is not int or not 0<price<2**128:
        raise ValueError("invalid source active-bin capacity")
    if capacity<2:
        return []
    # Do not silently ignore matching order liquidity even on a partial
    # MM fill: the hint is explicitly scoped to market-maker-only bins.
    if limit_order_support and bool(bin_record["limit_order_ask_side"])!=x_to_y and (
            bin_record["open_order_amount"] or bin_record["processed_order_remaining_amount"]):
        return []
    q=1<<64
    numerator,denominator=(price,q) if x_to_y else (q,price)
    if amount_in*numerator//denominator<=capacity:
        return []
    result=[]
    for target in sorted({max(1,capacity//2),max(1,capacity*3//4)}):
        candidate=(target*denominator+numerator-1)//numerator
        if not 0<candidate<amount_in or candidate in result:
            continue
        try:
            outcomes=[quote_bins(amount_in=candidate,swap_x_for_y=x_to_y,bins=[bin_record],
                        total_fee_rate=rate,max_bins=1,fee_on_input=fee_on_input,
                        limit_order_support=limit_order_support)
                      for rate in (0,MAX_FEE_NUMERATOR)]
        except ValueError:
            continue
        if all(0<o["amount_out"]<capacity and o["exact_input_filled"] for o in outcomes):
            result.append(candidate)
    return result


def source_active_bin_size_plan(fixture,*,amount_in):
    from arb.fixture_quote_execution_pipeline import extract_pool_states
    from arb.meteora_dlmm_bin_preflight import (active_bin_array_index,
        verified_bitmap_extension_address,verify_directional_bin_snapshot)
    from arb.meteora_dlmm_source_fee_decoder import static_parameters,limit_order_supported
    rows=extract_pool_states(fixture)
    if not rows or rows[0]["venue"]!="meteora_dlmm" or any(fixture.get(k) is not False for k in SAFE):
        raise ValueError("first-leg authenticated DLMM source required")
    row=rows[0];pool=row["address"];state=row["decoded_pool_state"]
    mint=fixture["route_mints"][0]
    direction=mint==state["token_x_mint"]
    if mint not in (state["token_x_mint"],state["token_y_mint"]):
        raise ValueError("DLMM active-bin size mint mismatch")
    proof=fixture["leg_evidence_by_index"][0]["auxiliary"]
    if (proof.get("bitmap_extension_source",{}).get("status")!="SOURCE_BITMAP_EXTENSION_ABSENT"
            or verified_bitmap_extension_address(pool,proof,fixture) is not None):
        raise ValueError("DLMM active-bin sizing requires observed extension absence")
    source=proof["directional_bin_source"]
    active=state["active_id"];index=active_bin_array_index(active)
    if source["input_is_x"] is not direction or source["active_bin_array_index"]!=index:
        raise ValueError("DLMM active-bin sizing source direction mismatch")
    verify_directional_bin_snapshot(pool,source,fixture["accounts"])
    decoded=decode_from_fixture(fixture,pool=pool,array_index=index)
    bin_record=decoded["bins"][active%70]
    raw=base64.b64decode(fixture["accounts"][pool]["data"][0],validate=True)
    mode=static_parameters(raw)["collect_fee_mode"]
    if mode not in (0,1):
        raise ValueError("unsupported DLMM fee collection mode")
    candidates=bounded_active_bin_input_candidates(bin_record,amount_in=amount_in,
        x_to_y=direction,fee_on_input=(mode==0 or not direction),
        limit_order_support=limit_order_supported(raw))
    return {"status":"SOURCE_DLMM_ACTIVE_BIN_SIZE_HINT_ONLY","pool":pool,
        "source_slot":row["snapshot_slot"],"manifest_sha256":fixture["state_account_manifest_sha256"],
        "input_mint":mint,"input_base_units":amount_in,"active_bin_id":active,
        "active_bin_array":decoded["bin_array_pda"],"price_q64":str(bin_record["price_q64"]),
        "output_capacity":bin_record["amount_y" if direction else "amount_x"],
        "candidate_amounts":candidates,"protocol_exact_verified":False,**SAFE}
