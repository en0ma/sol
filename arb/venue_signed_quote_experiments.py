"""Empirical venue quote experiments against actual isolated Surfpool signed swaps.

Consumes independently accepted signed receipts and manifest-bound pool quotes.
No fixture, mocked output or quote inference can masquerade as a swap sample.
"""
from arb.m5_three_venue_signed_quote_parity import compare
SAFE={"actionable":False,"live_execution_approved":False,"broadcast":False}

def measure(fixture,receipt,*,observed_unix,parity_report=None):
    # The caller can supply the parity computed for this exact signed batch.
    # Never trust it without independently checking the signed receipt.
    from arb.m5_three_distinct_venue_signed_acceptance import verify
    verify(fixture,receipt)
    report=parity_report if parity_report is not None else compare(
        fixture,receipt,observed_unix=observed_unix)
    if report.get("signed_execution_accepted") is not True:
        raise ValueError("signed execution not accepted for price experiment")
    if report.get("route_venues") not in (None,fixture.get("route_venues")):
        raise ValueError("parity route venues disagree with source fixture")
    if len(report.get("leg_comparisons",[]))!=3:
        raise ValueError("three signed venue legs required")
    rows=[]
    for leg in report.get("leg_comparisons",[]):
        observed=leg.get("signed_output_base_units")
        quoted=leg.get("quoted_output_base_units")
        valid=(report.get("signed_execution_accepted") is True
               and type(observed) is int and observed>0
               and type(quoted) is int and quoted>0
               and type(leg.get("signed_input_base_units")) is int
               and type(leg.get("signed_minus_quote_base_units")) is int
               and leg["signed_minus_quote_base_units"]==observed-quoted
               and leg.get("leg_index") in (0,1,2)
               and leg.get("venue")==fixture["route_venues"][leg["leg_index"]]
               and leg.get("pool")==fixture["route_pool_addresses"][leg["leg_index"]])
        row={"venue":leg.get("venue"),"pool":leg.get("pool"),
             "leg_index":leg.get("leg_index"),
             "source_manifest_sha256":fixture.get("state_account_manifest_sha256"),
             "source_slot":fixture.get("state_accounts_observed_slot"),
             "signed_simulation_accepted":report.get("signed_execution_accepted") is True,
             "signed_input_base_units":leg.get("signed_input_base_units"),
             "signed_output_base_units":observed,
             "predicted_output_base_units":quoted,
             "sample_status":"SIGNED_FORK_QUOTE_COMPARISON" if valid else "SAMPLE_BLOCKED",
             "integer_delta_base_units":observed-quoted if valid else None,
             "exact_integer_match":observed==quoted if valid else None,
             "source_exact_protocol_verified":False,
             "reason":leg.get("reason"),**SAFE}
        rows.append(row)
    return {"status":"SIGNED_FORK_PRICING_EXPERIMENT",
            "signed_execution_accepted":report.get("signed_execution_accepted") is True,
            "observed_compared_samples":sum(x["sample_status"]=="SIGNED_FORK_QUOTE_COMPARISON" for x in rows),
            "exact_integer_matches":sum(x["exact_integer_match"] is True for x in rows),
            "independently_validated_protocol_exact_samples":0,
            "venue_samples":rows,**SAFE}
