"""Offline fixture -> venue decode -> indicative quote -> signed-receipt audit.

Raw pool accounts are decoded from manifest-verified source fixture. Venue-
specific dynamic fee, vault, bin/tick, and OpenBook effective-reserve inputs
require an independently supplied decoder deriving them from this very same
fixture; no forged fee/price fields are filled in. A synthetic decoder is NOT
source authentication. Incompatible receipts return UNVERIFIED.
"""
import base64
from arb.source_snapshot_manifest import verify
from arb.next_ten_fork_pool_probe import PROGRAMS,DECODERS,MINT_KEYS
from arb.authenticated_quote_provider import from_snapshot
from arb.fixture_quote_binding import bind
from arb.quote_simulation_reconciliation import reconcile
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def extract_pool_states(fixture):
    verify(fixture)
    if fixture.get("source")!="READ_ONLY_MAINNET_BACKED_SURFPOOL":
        raise ValueError("unsupported source")
    addresses=fixture["state_account_addresses"]
    accounts=fixture["accounts"]
    rows=[]
    for key in ("first","second"):
        venue=fixture[key+"_venue"];pool=fixture[key+"_pool"]
        if venue not in PROGRAMS or pool not in addresses:
            raise ValueError("route pool absent from authenticated source inventory")
        acct=accounts[pool]
        if acct.get("owner")!=PROGRAMS[venue] or acct.get("executable") is not False:
            raise ValueError("pool source owner invalid")
        encoded=acct.get("data")
        if not isinstance(encoded,list) or len(encoded)!=2 or encoded[1]!="base64":
            raise ValueError("source pool is not base64 encoded")
        state=DECODERS[venue](base64.b64decode(encoded[0],validate=True))
        mints=[state[x] for x in MINT_KEYS[venue]]
        if len(set(mints))!=2 or set(mints)!=set(fixture["route_mints"][:2]):
            raise ValueError("decoded pool mints mismatch route")
        rows.append({"venue":venue,"address":pool,"mints":mints,
                     "decoded_pool_state":state,
                     "snapshot_slot":fixture["state_accounts_observed_slot"]})
    return rows

def evaluate(fixture,receipt,*,initial_input,as_of_unix,derive_pricing_state,
             tolerance_bps=100):
    if type(initial_input)is not int or not 0<initial_input<2**64 or type(as_of_unix)is not int:
        raise ValueError("valid amount and observation timestamp required")
    if not callable(derive_pricing_state):
        raise ValueError("independent source-backed venue fee/reserve decoder required")
    decoded=extract_pool_states(fixture)
    snapshots=[]
    for item in decoded:
        # The decoder gets the immutable captured account inventory. It must
        # supply actual account-derived fee/reserve/tick/bin evidence. The
        # caller is responsible for validating each returned field.
        state=derive_pricing_state(item,fixture)
        if not isinstance(state,dict):
            raise ValueError("missing venue-specific account-derived pricing state")
        forbidden={"venue","address","mints","slot","observed_unix",
                   "source_authenticated","verified","account_owner_verified",
                   "snapshot_origin"}
        if set(state)&forbidden:
            raise ValueError("pricing decoder cannot override source identity")
        snapshots.append({**state,"venue":item["venue"],"address":item["address"],
                          "mints":item["mints"],"slot":item["snapshot_slot"],
                          "observed_unix":as_of_unix,"verified":True,
                          "source_authenticated":True,"account_owner_verified":True,
                          "snapshot_origin":"READ_ONLY_MAINNET_BACKED_SURFPOOL"})
    quote,registry=from_snapshot(snapshots,now=as_of_unix,max_age=60)
    if registry["pool_count"]!=2:
        raise ValueError("source pool snapshot rejected by registry")
    m=fixture["route_mints"]
    legs=[{"venue":fixture["first_venue"],"pool":fixture["first_pool"],
           "input_mint":m[0],"output_mint":m[1]},
          {"venue":fixture["second_venue"],"pool":fixture["second_pool"],
           "input_mint":m[1],"output_mint":m[2]}]
    route={"start_mint":m[0],"legs":legs}
    quoted=[]
    for leg in legs:
        quoted.append(quote(leg,initial_input if not quoted else quoted[-1]["amount_out"]))
    identity=bind(fixture,route,quoted)
    # IMPORTANT: old signed receipts have source_snapshot_slot=None;
    # simply copying it from the fixture is forbidden. No quote proof
    # unless a separately authenticated signed receipt has that field.
    result=reconcile(route,quoted,receipt,tolerance_bps=tolerance_bps)
    return {"status":result["status"],"decoded_venues":[x["venue"] for x in decoded],
            "quotes":quoted,"source_binding":identity,"reconciliation":result,
            "actual_pricing_state_decoder_validated":False,
            "complete_seven_venue_accuracy_verified":False,**SAFE}
