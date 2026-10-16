"""On-fork Orca quote-to-signed-simulation probe. NEVER broadcasts swaps.

This diagnostic intentionally treats unavailable tick arrays, mismatched account
snapshots, and model rounding errors as evidence gaps rather than profitable
opportunities. Live quote accuracy is not assumed.
"""
import json
import os
from urllib.parse import urlparse
from arb.orca_whirlpool import fetch_pool
from arb.whirlpool_ticks import inspect
from arb.orca_multitick_quote import quote_from_decoded_arrays
from arb.orca_quote_reconcile import compare_quote_and_simulation
from arb.whirlpool_simulation import run


def probe(rpc, pool, amount=1000000):
    url = urlparse(rpc)
    if (url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost')
            or url.port != 8899 or url.username or url.password):
        raise ValueError('only loopback Surfpool RPC port 8899 is allowed')
    if type(amount) is not int or not 0 < amount <= 100000000:
        raise ValueError('invalid local swap size')
    state = fetch_pool(rpc, pool)
    sim = run(rpc, pool, input_amount=amount)
    if sim.get('swap_success') is not True:
        return {'status': 'SIMULATION_UNAVAILABLE', 'simulation_status': sim.get('status'),
                'quote_verified': False, 'actionable': False}
    evidence = inspect(rpc, pool)
    if evidence.get('pool_state') != state:
        return {'status': 'POOL_STATE_CHANGED', 'quote_verified': False, 'actionable': False}
    mint_in = state['token_mint_a'] if sim['direction'] == 'a_to_b' else state['token_mint_b']
    try:
        quote = quote_from_decoded_arrays(state, mint_in, amount, evidence['arrays'])
        compared = compare_quote_and_simulation(quote, sim)
    except (ValueError, KeyError, TypeError) as exc:
        return {'status': 'QUOTE_UNAVAILABLE', 'reason': str(exc)[:180],
                'quote_verified': False, 'actionable': False}
    return {'status': 'COMPARED', 'comparison': compared,
            'ticks_crossed': quote['ticks_crossed'],
            'tick_arrays_examined': quote['tick_arrays_examined'],
            'quote_verified': compared['status'] == 'MATCH',
            'actionable': False, 'confirmed_profitable': False}


def main():
    rpc = os.environ.get('SOLANA_RPC_URL', 'http://127.0.0.1:8899')
    with open('arb/whirlpool_pools.json') as file:
        pools = json.load(file)['pools']
    sizes = (100000, 1000000, 5000000, 20000000, 50000000)
    results = []
    for pool in pools:
        for amount in sizes:
            result = probe(rpc, pool['address'], amount=amount)
            results.append({'pool': pool['address'], 'input_base_units': amount, **result})
    report = {'status': 'COMPARED' if any(r.get('status') == 'COMPARED' for r in results) else 'NO_COMPARABLE_QUOTE',
              'attempted_pools': len(pools), 'attempted_pool_sizes': len(results),
              'tested_input_base_units': list(sizes),
              'exact_matches': sum(r.get('comparison', {}).get('status') == 'MATCH' for r in results),
              'mismatches': sum(r.get('comparison', {}).get('status') == 'MISMATCH' for r in results),
              'matched_tick_crossing_quotes': sum(r.get('comparison', {}).get('status') == 'MATCH' and r.get('ticks_crossed', 0) > 0 for r in results),
              'unavailable_quotes': sum(r.get('status') == 'QUOTE_UNAVAILABLE' for r in results),
              'unavailable_simulations': sum(r.get('status') == 'SIMULATION_UNAVAILABLE' for r in results),
              'results': results, 'executable_quotes_verified': 0,
              'confirmed_profitable': 0}
    print(json.dumps(report, indent=2))
    destination = os.environ.get('ORCA_QUOTE_COMPARISON_REPORT')
    if destination:
        with open(destination, 'w') as file:
            json.dump(report, file, indent=2)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
