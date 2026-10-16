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
    prepared = []
    for t in ticks:
        if not isinstance(t, dict) or type(t.get('sqrt_price_x64')) is not int or type(t.get('liquidity_net')) is not int or type(t.get('tick_index')) is not int:
            raise ValueError('incomplete tick metadata')
        target, net = t['sqrt_price_x64'], t['liquidity_net']
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
        if crosses >= max_crossings:
            raise ValueError('crossing budget exceeded')
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
