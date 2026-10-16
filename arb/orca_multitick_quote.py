"""Conservative integer exact-input Whirlpool multi-tick quote prototype.

All tick sqrt prices and signed liquidity deltas must come from separately
validated, slot-consistent accounts. This pure model does not prove those inputs,
match all Whirlpool fee rounding, build swaps or authorize execution.
"""

Q = 1 << 64
FEE_DENOM = 1_000_000


def _ceil(n, d):
    return (n + d - 1) // d


def quote_multitick(state, mint_in, amount_in, ticks, *, max_crossings=12):
    """Consume exact input across ordered initialized ticks, failing closed.

    ticks: [{'tick_index': int, 'sqrt_price_x64': int,
             'liquidity_net': int}, ...] in swap traversal order. All values
    must be decoded and externally verified before use.
    """
    if type(amount_in) is not int or not 0 < amount_in < (1 << 64):
        raise ValueError('invalid exact input amount')
    if type(max_crossings) is not int or not 0 <= max_crossings <= 64:
        raise ValueError('invalid crossing budget')
    if not isinstance(ticks, list) or len(ticks) > 64:
        raise ValueError('invalid tick budget')
    a, b = state['token_mint_a'], state['token_mint_b']
    if mint_in not in (a, b):
        raise ValueError('mint not in pool')
    down = mint_in == a
    p, liquidity, fee = int(state['sqrt_price_x64']), int(state['liquidity']), state['fee_rate_hundredths_bps']
    if not 0 < p < (1 << 128) or not 0 < liquidity < (1 << 128):
        raise ValueError('invalid price or liquidity')
    if type(fee) is not int or not 0 <= fee < FEE_DENOM:
        raise ValueError('invalid fee')
    previous = p
    previous_index = state.get("tick_current_index")
    if type(previous_index) is not int:
        raise ValueError("missing current tick index")
    prepared = []
    for t in ticks:
        if not isinstance(t, dict) or type(t.get('sqrt_price_x64')) is not int or type(t.get('liquidity_net')) is not int or type(t.get('tick_index')) is not int:
            raise ValueError('incomplete tick metadata')
        target, net = t['sqrt_price_x64'], t['liquidity_net']
        index = t["tick_index"]
        if not (index <= previous_index if down else index > previous_index):
            raise ValueError("unordered or wrong-direction tick index")
        previous_index = index
        if not 0 < target < (1 << 128) or not (-1 << 127) <= net < (1 << 127):
            raise ValueError('invalid tick price or liquidity net')
        if not (target < previous if down else target > previous):
            raise ValueError('unordered or wrong-direction tick price')
        previous = target
        prepared.append((target, net, t['tick_index']))
    if not prepared:
        raise ValueError('missing initialized tick coverage')
    remaining, output, crosses, steps = amount_in, 0, 0, []
    for target, net, tick_index in prepared:
        required_net = (_ceil(liquidity * Q * (p - target), p * target)
                        if down else _ceil(liquidity * (target - p), Q))
        if required_net <= 0:
            raise ValueError('invalid zero-input crossing')
        required_gross = _ceil(required_net * FEE_DENOM, FEE_DENOM - fee)
        if remaining < required_gross:
            effective = remaining - _ceil(remaining * fee, FEE_DENOM)
            if effective <= 0:
                raise ValueError('input consumed by fees')
            if down:
                next_p = _ceil(liquidity * Q * p, liquidity * Q + effective * p)
                step_out = liquidity * (p - next_p) // Q
            else:
                next_p = p + effective * Q // liquidity
                step_out = liquidity * Q * (next_p - p) // (p * next_p)
            if not (target < next_p < p if down else p < next_p < target):
                raise ValueError('partial step reached tick unexpectedly')
            if step_out <= 0:
                raise ValueError('dust output')
            output += step_out
            steps.append({'kind': 'partial', 'input': remaining, 'output': step_out,
                          'post_sqrt_price_x64': str(next_p)})
            remaining = 0
            p = next_p
            break
        if crosses >= max_crossings:
            raise ValueError("crossing budget exceeded")
        if down:
            step_out = liquidity * (p - target) // Q
        else:
            step_out = liquidity * Q * (target - p) // (p * target)
        if step_out <= 0:
            raise ValueError('dust at tick crossing')
        next_liquidity = liquidity - net if down else liquidity + net
        if not 0 < next_liquidity < (1 << 128):
            raise ValueError('invalid liquidity following tick crossing')
        remaining -= required_gross
        output += step_out
        crosses += 1
        steps.append({'kind': 'cross', 'tick_index': tick_index,
                      'input': required_gross, 'output': step_out,
                      'liquidity_after': str(next_liquidity)})
        liquidity, p = next_liquidity, target
        if remaining == 0:
            break
    if remaining != 0:
        raise ValueError('missing tick coverage for remaining input')
    return {'status': 'INDICATIVE_MULTITICK_ONLY', 'mint_in': mint_in,
            'mint_out': b if down else a, 'amount_in': amount_in,
            'estimated_output_base_units': output, 'ticks_crossed': crosses,
            'post_sqrt_price_x64': str(p), 'post_liquidity': str(liquidity),
            'steps': steps, 'actionable': False, 'executable_quote': False,
            'simulation_verified': False}


def quote_from_decoded_arrays(state, mint_in, amount_in, arrays, sqrt_price_at_tick=None,
                              *, max_crossings=12):
    """Bridge validated tick observations to the indicative multi-tick model.

    The price converter is an injected, independently verified tick-math
    implementation. Missing or unsupported arrays, unaligned tick indexes,
    and gaps in the array traversal fail closed. No on-chain validation is
    implied by providing a callback, and the result is never executable.
    """
    from arb.whirlpool_ticks import ARRAY_TICKS, start_tick
    if sqrt_price_at_tick is None:
        from arb.orca_tick_math import sqrt_price_from_tick_index
        sqrt_price_at_tick = sqrt_price_from_tick_index
    if not callable(sqrt_price_at_tick):
        raise ValueError("missing tick price converter")
    if not isinstance(arrays, list) or not 1 <= len(arrays) <= 5:
        raise ValueError("invalid array coverage")
    spacing = state.get("tick_spacing")
    current = state.get("tick_current_index")
    if type(spacing) is not int or spacing <= 0 or type(current) is not int:
        raise ValueError("invalid Whirlpool tick metadata")
    if mint_in not in (state["token_mint_a"], state["token_mint_b"]):
        raise ValueError("mint not in pool")
    down = mint_in == state["token_mint_a"]
    span = ARRAY_TICKS * spacing
    indexed = {}
    for entry in arrays:
        if not isinstance(entry, dict) or type(entry.get("start_tick")) is not int:
            raise ValueError("invalid decoded tick array")
        start = entry["start_tick"]
        if start % span or start in indexed:
            raise ValueError("duplicate or unaligned tick array")
        indexed[start] = entry
    start = start_tick(current, spacing)
    step = -span if down else span
    ticks = []
    covered = 0
    while covered < len(indexed):
        entry = indexed.get(start)
        if entry is None or entry.get("status") != "FIXED_VALID":
            raise ValueError("missing or unsupported tick array")
        records = entry.get("ticks")
        if not isinstance(records, list):
            raise ValueError("missing decoded ticks")
        local = []
        seen = set()
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("invalid tick record")
            ix, net = record.get("tick_index"), record.get("liquidity_net")
            if (type(ix) is not int or ix in seen or not start <= ix < start + span
                    or (ix-start) % spacing):
                raise ValueError("invalid initialized tick index")
            seen.add(ix)
            if type(net) is not str or not net.lstrip("-").isdigit():
                raise ValueError("invalid tick liquidity")
            if (ix <= current if down else ix > current):
                price = sqrt_price_at_tick(ix)
                if type(price) is not int:
                    raise ValueError("invalid converted tick price")
                local.append({"tick_index": ix, "sqrt_price_x64": price,
                              "liquidity_net": int(net)})
        ticks.extend(sorted(local, key=lambda t: t["tick_index"], reverse=down))
        covered += 1
        start += step
    result = quote_multitick(state, mint_in, amount_in, ticks,
                             max_crossings=max_crossings)
    return {**result, "tick_arrays_examined": covered,
            "source": "SUPPLIED_ARRAYS_AND_REFERENCE_TICK_MATH",
            "actionable": False, "executable_quote": False}
