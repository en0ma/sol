"""Bound positive indicative gross candidates by observed quote-model error.

An observed discrepancy on one CLMM direction is not a universal slippage
estimate. This conservative diagnostic suppresses promotion of candidates
whose entire gross margin is smaller than the measured quote shortfall.
It does not make surviving routes executable.
"""
def classify(gross,observed_shortfall_bps,final_amount):
    if (type(gross)is not int or type(observed_shortfall_bps)is not int or
            type(final_amount)is not int or final_amount<=0 or
            not 0<=observed_shortfall_bps<=10000):
        raise ValueError("invalid CLMM uncertainty diagnostic")
    buffer=(final_amount*observed_shortfall_bps+9999)//10000
    return {"gross_base_units":gross,"reference_quote_error_bps":observed_shortfall_bps,
            "reference_error_buffer_base_units":buffer,
            "gross_exceeds_reference_error":gross>buffer,
            "reference_only":True,"actionable":False,
            "simulation_verified":False}
