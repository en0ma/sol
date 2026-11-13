"""Source-fixture PumpSwap FeeConfig parser: provenance-aware, not effective fee.

Config address MUST be pool-linked and its program owner explicitly verified.
Fee modes and capitalization thresholds remain unresolved until independent
market-cap and PDA derivation attestations are available.
"""
import base64
from arb.source_snapshot_manifest import verify
from arb.pumpswap_fee_config import decode
from arb.pumpswap_fee_account import PROGRAM
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}
def inspect(fixture,*,config_address,expected_program=PROGRAM):
    verify(fixture)
    if type(config_address)is not str or config_address not in fixture["state_account_addresses"]:
        raise ValueError("fee account not source-inventory captured")
    if expected_program!=PROGRAM:
        raise ValueError("fee owner program mismatch")
    info=fixture["accounts"][config_address]
    if info.get("owner")!=PROGRAM or info.get("executable") is not False:
        raise ValueError("fee account owner invalid")
    data=info.get("data")
    if not isinstance(data,list) or len(data)!=2 or data[1]!="base64":
        raise ValueError("fee data encoding invalid")
    fees=decode(base64.b64decode(data[0],validate=True))
    return {"status":"CAPTURED_PUMP_FEE_CONFIG_PARSED",
       "fee_account":config_address,"source_slot":fixture["state_accounts_observed_slot"],
       "flat_fees":fees["flat_fees"],"standard_tier_count":len(fees["fee_tiers"]),
       "stable_tier_count":len(fees["stable_fee_tiers"]),
       "effective_fee_authenticated":False,
       "fee_config_pda_verified":False,
       "market_cap_tier_verified":False,**SAFE}
