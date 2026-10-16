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
    if evidence['pool_tick'] != state['tick_current_index']:
        return {'status': 'POOL_STATE_CHANGED', 'quote_verified': False, 'actionable': False}
    mint_in = state['token_mint_a'] if sim['direction'] == 'a_to_b' else state['token_mint_b']
    try:
        quote = quote_from_decoded_arrays(state, mint_in, amount, evidence['arrays'])
        compared = compare_quote_and_simulation(quote, sim)
    except (ValueError, KeyError, TypeError) as exc:
        return {'status': 'QUOTE_UNAVAILABLE', 'reason': str(exc)[:180],
                'quote_verified': False, 'actionable': False}
    return {'status': 'COMPARED', 'comparison': compared,
            'quote_verified': compared['status'] == 'MATCH',
            'actionable': False, 'confirmed_profitable': False}


def main():
    rpc = os.environ.get('SOLANA_RPC_URL', 'http://127.0.0.1:8899')
    with open('arb/whirlpool_pools.json') as file:
        pools = json.load(file)['pools']
    print(json.dumps([probe(rpc, pool['address']) for pool in pools], indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
