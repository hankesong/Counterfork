"""Compound v2 UTC-day liquidation inventory. Standard library; read-only RPC."""
import argparse
import hashlib
import html
import json
import random
import re
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from phase0_check import ROOT, save
from phase1_single import address, calldata, cast, load, words
from locate_phase0_sample import CDAI, COMPTROLLER, TOPIC, block
from rpc_cache import rpc
from rpc_transport import STATS, redact, rate_limit
from phase2_contract import analyzed_borrowers, display, provenance, require_evidence

DIR = ROOT / 'data/phase2'
NOTE = 'N−1 预言机价格估值，仅用于排序，不等于清算实际价格'
SIGNATURE = 'LiquidateBorrow(address,address,uint256,address,uint256)'
getcontext().prec = 100
STEP_START = time.monotonic()
WEB_REQUESTS = 0


def check_time():
    if time.monotonic() - STEP_START > 1740:
        raise RuntimeError('29-minute step deadline reached; caches retained; stop and report alternatives')


def call(target, signature, n, *args):
    check_time()
    return rpc('eth_call', [{'to': target, 'data': calldata(signature, *args)}, hex(n)])


def utc(stamp):
    return datetime.fromtimestamp(stamp, timezone.utc).isoformat()


def source(target, label):
    """Keep HTML private; publish only verified source/ABI and provenance."""
    global WEB_REQUESTS
    path = DIR / (label + '_verification.json')
    if path.exists():
        proof = load(path)
        code = (DIR / (label + '_source.sol')).read_text(encoding='utf-8')
        assert hashlib.sha256(code.encode()).hexdigest() == proof['source_sha256']
        assert proof['address'].lower() == target.lower()
        return code, load(DIR / (label + '_abi.json'))
    page = ROOT / 'data/private' / ('phase2_' + label + '.html')
    url = 'https://etherscan.io/address/' + target + '#code'
    if not page.exists():
        rate_limit()
        WEB_REQUESTS += 1
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
            page.write_bytes(response.read())
    text = page.read_text(encoding='utf-8')
    assert target.lower() in text.lower()
    assert 'Source Code Verified' in text and 'Exact Match' in text, 'Etherscan source not Exact Match'

    class Parser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.codes, self.pres, self.current = [], [], None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if attrs.get('data-csource'):
                self.codes.append(attrs['data-csource'])
            if tag == 'pre':
                self.current = []

        def handle_data(self, data):
            if self.current is not None:
                self.current.append(data)

        def handle_endtag(self, tag):
            if tag == 'pre' and self.current is not None:
                self.pres.append(''.join(self.current))
                self.current = None

    parser = Parser()
    parser.feed(text)
    codes = parser.codes or [p for p in parser.pres if 'pragma solidity' in p]
    code = '\n\n'.join(dict.fromkeys(codes))
    assert code, 'No verified Solidity source parsed'
    abi = next(json.loads(p) for p in parser.pres if p.strip().startswith('[{"'))
    (DIR / (label + '_source.sol')).write_text(code, encoding='utf-8')
    save(DIR / (label + '_abi.json'), abi)
    save(path, {'address': target.lower(), 'source_url': url, 'verification': 'Exact Match',
                'source_sha256': hashlib.sha256(code.encode()).hexdigest()})
    return code, abi


def abi_function(abi, name, types=()):
    found = [x for x in abi if x['type'] == 'function' and x['name'] == name
             and [i['type'] for i in x['inputs']] == list(types)]
    assert len(found) == 1, 'Missing verified ABI function: ' + name
    return name + '(' + ','.join(types) + ')'


def first_at(stamp):
    lo, hi = 11300000, 11370000
    assert int(block(lo)['timestamp'], 16) < stamp <= int(block(hi)['timestamp'], 16)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if int(block(mid)['timestamp'], 16) < stamp:
            lo = mid
        else:
            hi = mid
    assert int(block(lo)['timestamp'], 16) < stamp <= int(block(hi)['timestamp'], 16)
    return hi


def string_result(raw):
    data = bytes.fromhex(raw[2:])
    if len(data) == 32:
        return data.rstrip(b'\0').decode('utf-8')
    offset = int.from_bytes(data[:32], 'big')
    size = int.from_bytes(data[offset:offset + 32], 'big')
    assert offset == 32 and size <= len(data) - offset - 32
    return data[offset + 32:offset + 32 + size].decode('utf-8')


def prepare():
    start_ts = int(datetime(2020, 11, 26, tzinfo=timezone.utc).timestamp())
    start, end = first_at(start_ts), first_at(start_ts + 86400) - 1
    window = {'start_utc': utc(start_ts), 'end_utc': utc(start_ts + 86399),
              'block_count': str(end - start + 1)}
    for label, n in [('first', start), ('last', end), ('preceding', start - 1), ('following', end + 1)]:
        h = block(n)
        window[label] = {'block': str(n), 'timestamp': str(int(h['timestamp'], 16)),
                         'utc': utc(int(h['timestamp'], 16)), 'hash': h['hash']}
    save(DIR / 'window.json', window)
    code, proxy_abi = source(COMPTROLLER, 'unitroller')
    impl_sig = abi_function(proxy_abi, 'comptrollerImplementation')
    implementation = address(words(call(COMPTROLLER, impl_sig, start))[0])
    code, abi = source(implementation, 'comptroller')
    markets_sig = abi_function(abi, 'getAllMarkets')
    assert re.search(r'function\s+getAllMarkets\s*\(\s*\)', code)
    raw = words(call(COMPTROLLER, markets_sig, start))
    assert int(raw[0], 16) == 32 and len(raw) == 2 + int(raw[1], 16)
    markets = [address(x) for x in raw[2:]]
    assert len(markets) == len(set(markets)) and CDAI.lower() in markets
    oracle_sig = abi_function(abi, 'oracle')
    oracle = address(words(call(COMPTROLLER, oracle_sig, start))[0])
    oracle_code, oracle_abi = source(oracle, 'oracle')
    abi_function(oracle_abi, 'getUnderlyingPrice', ('address',))
    assert 'return mul(1e30, priceInternal(config)) / config.baseUnit;' in oracle_code
    rows = []
    for market in markets:
        code, token_abi = source(market, 'market_' + market[2:])
        symbol_sig = abi_function(token_abi, 'symbol')
        symbol = string_result(call(market, symbol_sig, start))
        decimals_sig = abi_function(token_abi, 'decimals')
        cdecimals = int(call(market, decimals_sig, start), 16)
        # Native ETH identification requires the verified CEther contract and payable API.
        if symbol == 'cETH':
            assert re.search(r'contract\s+CEther\s+is\s+CToken', code)
            assert not any(x.get('name') == 'underlying' for x in token_abi)
            assert re.search(r'function\s+mint\s*\(\s*\)\s+(?:external|public)\s+payable', code)
            underlying, usymbol, decimals = None, 'ETH', 18
            basis = 'Verified CEther payable mint uses msg.value (wei); native ETH has 18 decimals; ABI has no underlying()'
        else:
            underlying = address(words(call(market, abi_function(token_abi, 'underlying'), start))[0])
            # The same ERC20 selectors are verified above and independently called on underlying.
            usymbol = string_result(call(underlying, symbol_sig, start))
            decimals = int(call(underlying, decimals_sig, start), 16)
            basis = 'Historical underlying(), symbol(), decimals() eth_call at window first block'
        assert 0 <= decimals <= 36
        rows.append({'ctoken': market, 'ctoken_symbol': symbol, 'ctoken_decimals': str(cdecimals),
                     'underlying': underlying, 'symbol': usymbol, 'decimals': str(decimals), 'basis': basis})
        print(json.dumps({'market': symbol, 'underlying_symbol': usymbol, 'decimals': str(decimals)}), flush=True)
    # Verify the canonical event declaration in the historical cDAI implementation.
    cdai_abi = load(DIR / ('market_' + CDAI[2:].lower() + '_abi.json'))
    cdai_impl = address(words(call(CDAI.lower(), abi_function(cdai_abi, 'implementation'), start))[0])
    event_code, event_abi = source(cdai_impl, 'ctoken_implementation')
    event = next(x for x in event_abi if x['type'] == 'event' and x['name'] == 'LiquidateBorrow')
    verified_signature = event['name'] + '(' + ','.join(i['type'] for i in event['inputs']) + ')'
    assert verified_signature == SIGNATURE and all(not i['indexed'] for i in event['inputs'])
    assert cast('keccak', verified_signature) == TOPIC
    assert all('event LiquidateBorrow' in (DIR / ('market_' + m[2:] + '_source.sol')).read_text(encoding='utf-8')
               for m in markets)
    result = {'window': window, 'markets': rows, 'comptroller': COMPTROLLER.lower(),
              'comptroller_implementation': implementation, 'oracle_at_start': oracle,
              'event_signature': verified_signature, 'topic': TOPIC, 'getAllMarkets_signature': markets_sig}
    save(DIR / 'setup.json', result)
    return result


def main():
    global urlopen
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--cache-only', action='store_true', help='Fail on cache misses; forbid all RPC/web network access.')
    args = parser.parse_args()
    if args.cache_only:
        import rpc_cache
        def deny_network(*args, **kwargs):
            raise RuntimeError('Cache-only run: network access forbidden; required cache is missing')
        rpc_cache.exchange = deny_network
        urlopen = deny_network
    DIR.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    run = {'started_utc': utc(int(time.time())), 'stages': [], 'cache_only': args.cache_only}
    try:
        setup = stage('prepare', prepare, run)
        if not args.prepare_only:
            headers = stage('headers', lambda: fetch_headers(setup), run)
            logs = stage('logs', lambda: fetch_logs(setup, headers), run)
            events = stage('decode', lambda: decode(logs, setup, headers), run)
            checks = stage('receipts', lambda: receipts(events, headers), run)
            stage('valuation', lambda: value(events), run)
            stage('outputs', lambda: outputs(setup, events, checks, run), run)
        run['status'] = 'passed'
    except Exception as exc:
        run.update(status='failed', error=redact(exc))
        raise
    finally:
        run.update(rpc_requests_this_run=str(STATS['network_requests']),
                   cache_hits=str(STATS['cache_hits']), web_requests=str(WEB_REQUESTS),
                   elapsed_seconds=format(time.monotonic() - started, '.3f'))
        history = load(DIR / 'runs.json') if (DIR / 'runs.json').exists() else []
        history.append(run)
        save(DIR / 'runs.json', history)
        print(json.dumps(run, ensure_ascii=True), flush=True)
    if run['status'] == 'passed' and not args.prepare_only:
        from phase2_report import main as report
        report()


def stage(name, action, run):
    global STEP_START
    STEP_START = time.monotonic()
    before = STATS.copy()
    record = {'stage': name}
    print(json.dumps({'stage': name, 'status': 'started'}), flush=True)
    try:
        result = action()
        record['status'] = 'passed'
        return result
    except Exception as exc:
        record.update(status='failed', error=redact(exc))
        raise
    finally:
        record.update(elapsed_seconds=format(time.monotonic() - STEP_START, '.3f'),
                      rpc_requests=str(STATS['network_requests'] - before['network_requests']),
                      cache_hits=str(STATS['cache_hits'] - before['cache_hits']))
        run['stages'].append(record)
        save(DIR / 'progress.json', run)


def mapped(items, function, label):
    result = []
    with ThreadPoolExecutor(max_workers=16) as pool:
        # Keep a bounded queue full rather than waiting at every batch barrier.
        # All network starts still pass through the same global rate limiter.
        source_items = iter(items)
        pending = deque()
        for _ in range(min(64, len(items))):
            pending.append(pool.submit(function, next(source_items)))
        while pending:
            check_time()
            result.append(pending.popleft().result())
            item = next(source_items, None)
            if item is not None:
                pending.append(pool.submit(function, item))
            if len(result) % 96 == 0 or not pending:
                progress = {'stage': label, 'completed': str(len(result)), 'total': str(len(items)),
                            'rpc_requests_this_run': str(STATS['network_requests']),
                            'elapsed_seconds': format(time.monotonic() - STEP_START, '.3f')}
                save(DIR / 'scan_progress.json', progress)
                print(json.dumps(progress), flush=True)
    return result


def fetch_headers(setup):
    start, end = (int(setup['window'][key]['block']) for key in ('first', 'last'))
    numbers = list(range(start, end + 1))
    rows = mapped(numbers, block, 'headers')
    headers = dict(zip(numbers, rows))
    for n, h in headers.items():
        assert int(h['number'], 16) == n
        assert int(setup['window']['first']['timestamp']) <= int(h['timestamp'], 16) <= int(setup['window']['last']['timestamp'])
        if n > start:
            assert h['parentHash'] == headers[n - 1]['hash']
            assert int(h['timestamp'], 16) > int(headers[n - 1]['timestamp'], 16)
    return headers


def cache_path(method, params):
    key = hashlib.sha256(json.dumps([method, params], sort_keys=True).encode()).hexdigest()
    return ROOT / 'data/rpc' / (key + '.json')


def fetch_logs(setup, headers):
    markets = [x['ctoken'] for x in setup['markets']]
    old = {}
    # Require actual Phase 1 cache hits, never silently refetch its cDAI requests.
    for n in range(11332824, 11333317):
        params = [{'address': CDAI, 'topics': [TOPIC], 'blockHash': headers[n]['hash']}]
        assert cache_path('eth_getLogs', params).exists(), 'Missing required Phase 1 cDAI cache'
        assert cache_path('eth_getBlockByNumber', [hex(n), False]).exists()
        old[n] = rpc('eth_getLogs', params)

    def fetch(n):
        return rpc('eth_getLogs', [{'address': markets, 'topics': [TOPIC], 'blockHash': headers[n]['hash']}])

    chunks = mapped(list(headers), fetch, 'logs')
    result = []
    compare_keys = ('address', 'topics', 'data', 'blockHash', 'blockNumber',
                    'transactionHash', 'transactionIndex', 'logIndex')
    for n, logs in zip(headers, chunks):
        assert isinstance(logs, list)
        if n in old:
            def normalized(rows):
                return sorted([json.dumps({k: log[k] for k in compare_keys}, sort_keys=True)
                               for log in rows])
            assert normalized(old[n]) == normalized([log for log in logs if log['address'].lower() == CDAI.lower()]), 'Phase 1 cDAI log set differs'
        result.extend(logs)
    save(DIR / 'phase1_cache_check.json', {'blocks': '493', 'cdai_log_cache_hits': '493',
         'headers_cached': True, 'cdai_log_sets_match': True,
         'cdai_events': str(sum(len(rows) for rows in old.values())),
         'all_market_events_in_phase1_window': str(sum(len(rows) for n, rows in zip(headers, chunks) if n in old)),
         'scope_note': 'Phase 1 cached cDAI only; all-market array queries have distinct keys and require one new query per block on first run.'})
    return result


def decode(logs, setup, headers):
    markets = {x['ctoken']: x for x in setup['markets']}
    result, seen = [], set()
    for log in logs:
        n = int(log['blockNumber'], 16)
        h = headers[n]
        market = log['address'].lower()
        assert market in markets and log['topics'] == [TOPIC] and not log.get('removed', False)
        assert log['blockHash'] == h['hash']
        ti, li = int(log['transactionIndex'], 16), int(log['logIndex'], 16)
        assert h['transactions'][ti] == log['transactionHash']
        if 'blockTimestamp' in log:
            assert int(log['blockTimestamp'], 16) == int(h['timestamp'], 16)
        assert (n, li) not in seen, 'Duplicate event position'
        seen.add((n, li))
        data = words(log['data'])
        assert len(data) == 5
        collateral = address(data[3])
        assert collateral in markets, 'Collateral missing from starting market list'
        result.append({'tx_hash': log['transactionHash'], 'blockNumber': str(n),
            'blockHash': h['hash'], 'blockTimestamp': str(int(h['timestamp'], 16)),
            'block_utc': utc(int(h['timestamp'], 16)), 'transactionIndex': str(ti), 'logIndex': str(li),
            'liquidator': address(data[0]), 'borrower': address(data[1]),
            'repayAmount': str(int(data[2], 16)), 'repaid_market': market,
            'repaid_market_symbol': markets[market]['ctoken_symbol'],
            'underlying_symbol': markets[market]['symbol'], 'underlying_decimals': markets[market]['decimals'],
            'cTokenCollateral': collateral, 'collateral_market_symbol': markets[collateral]['ctoken_symbol'],
            'collateral_underlying_symbol': markets[collateral]['symbol'],
            'collateral_underlying_decimals': markets[collateral]['decimals'],
            'seizeTokens': str(int(data[4], 16)),
            'dai_related': CDAI.lower() in (market, collateral), 'raw_log': log})
    return sorted(result, key=lambda e: (int(e['blockNumber']), int(e['logIndex'])))


def receipts(events, headers):
    path = DIR / 'receipt_sample.json'
    fingerprint = hashlib.sha256(json.dumps([(e['tx_hash'], e['logIndex']) for e in events]).encode()).hexdigest()
    if path.exists():
        selection = load(path)
        assert selection['event_set_sha256'] == fingerprint
    else:
        seed = random.SystemRandom().getrandbits(128)
        picked = random.Random(seed).sample(events, 5)
        selection = {'seed': str(seed), 'method': 'Python random.Random(seed).sample(sorted events, 5)',
                     'event_set_sha256': fingerprint,
                     'events': [{'tx_hash': e['tx_hash'], 'logIndex': e['logIndex']} for e in picked]}
        save(path, selection)
    index = {(e['tx_hash'], e['logIndex']): e for e in events}
    for ref in selection['events']:
        e = index[(ref['tx_hash'], ref['logIndex'])]
        r = rpc('eth_getTransactionReceipt', [e['tx_hash']])
        assert r['status'] == '0x1' and r['transactionHash'] == e['tx_hash']
        assert r['blockHash'] == e['blockHash'] and str(int(r['blockNumber'], 16)) == e['blockNumber']
        assert str(int(r['transactionIndex'], 16)) == e['transactionIndex']
        keys = ('address', 'topics', 'data', 'blockNumber', 'blockHash', 'transactionHash', 'transactionIndex', 'logIndex')
        assert any(all(log[k] == e['raw_log'][k] for k in keys) for log in r['logs'])
        ref.update(blockNumber=e['blockNumber'], verified=True)
    save(path, selection)
    return selection


def value(events):
    blocks = sorted({int(e['blockNumber']) - 1 for e in events})
    oracles = dict(zip(blocks, mapped(blocks,
        lambda n: address(words(call(COMPTROLLER, 'oracle()', n))[0]), 'oracle_addresses')))
    keys = sorted({(int(e['blockNumber']) - 1, e['repaid_market']) for e in events})
    prices = dict(zip(keys, mapped(keys,
        lambda key: int(call(oracles[key[0]], 'getUnderlyingPrice(address)', key[0], key[1]), 16), 'prices')))
    for e in events:
        n = int(e['blockNumber']) - 1
        price = prices[(n, e['repaid_market'])]
        assert price > 0, 'Nonpositive oracle price'
        e.update(oracle_block=str(n), oracle=oracles[n], oracle_price_raw=str(price),
                 oracle_price_usd=decimal_scaled(price, 36 - int(e['underlying_decimals'])),
                 repay_usd_estimate=decimal_scaled(int(e['repayAmount']) * price, 36),
                 valuation_note=NOTE)
    save(DIR / 'price_pairs.json', [{'block': str(n), 'market': market, 'oracle': oracles[n],
         'price_raw': str(prices[(n, market)])} for n, market in keys])


def decimal_scaled(value, scale):
    return format(Decimal(value) / Decimal(10**scale), 'f')


def totals(events):
    return {'event_count': str(len(events)), 'borrower_count': str(len({e['borrower'] for e in events})),
            'repay_usd_estimate': decimal_scaled(sum(int(e['repayAmount']) * int(e['oracle_price_raw']) for e in events), 36)}


def outputs(setup, events, checks, run=None):
    proof = provenance(DIR, STATS['network_requests'], run)
    analyzed = analyzed_borrowers()
    groups = {}
    for e in events:
        e['display'] = display(e)
        groups.setdefault(e['borrower'], []).append(e)
    accounts = []
    for borrower, rows in groups.items():
        accounts.append({'borrower': borrower, 'liquidation_count': str(len(rows)),
            'status': 'analyzed' if borrower.lower() in analyzed else 'pending',
            'first_liquidation_block': rows[0]['blockNumber'], 'last_liquidation_block': rows[-1]['blockNumber'],
            'repay_usd_estimate_total': totals(rows)['repay_usd_estimate'],
            'dai_related': any(e['dai_related'] for e in rows), 'valuation_note': NOTE,
            'events': [{'tx_hash': e['tx_hash'], 'logIndex': e['logIndex']} for e in rows]})
    accounts.sort(key=lambda a: (-Decimal(a['repay_usd_estimate_total']), a['borrower']))
    for i, a in enumerate(accounts, 1):
        a.update(rank=str(i), top20=i <= 20)
    sample = load(ROOT / 'data/phase1/sample.json')
    matched = [e for e in events if e['tx_hash'] == sample['liquidation_transaction']
               and e['logIndex'] == str(int(sample['log']['logIndex'], 16))]
    assert len(matched) == 1
    e = matched[0]
    mapping = {'tx_hash': 'liquidation_transaction', 'blockNumber': 'liquidation_block',
               'blockHash': 'liquidation_block_hash', 'block_utc': 'liquidation_timestamp_utc',
               'transactionIndex': 'transaction_index', 'liquidator': 'liquidator', 'borrower': 'borrower',
               'repayAmount': 'repayAmount', 'cTokenCollateral': 'cTokenCollateral', 'seizeTokens': 'seizeTokens'}
    assert all(e[key] == str(sample[source_key]) for key, source_key in mapping.items())
    assert e['raw_log'] == sample['log'], 'Phase 1 raw log differs'
    dai_repaid = [row for row in events if row['repaid_market'] == CDAI.lower()]
    maximum = max(dai_repaid, key=lambda row: int(row['repayAmount']))
    total, related, repaid = totals(events), totals([r for r in events if r['dai_related']]), totals(dai_repaid)
    comparison = {'public_report_total_usd': '89000000', 'public_report_dai_related_usd': '52000000',
        'total_difference_usd': format(Decimal(total['repay_usd_estimate']) - Decimal(89000000), 'f'),
        'dai_related_difference_usd': format(Decimal(related['repay_usd_estimate']) - Decimal(52000000), 'f'),
        'dai_repaid_difference_usd': format(Decimal(repaid['repay_usd_estimate']) - Decimal(52000000), 'f'),
        'source': 'https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound'}
    cross = {'phase1_sample_fields_match': True, 'phase1_raw_log_exact_match': True,
             'phase1_is_largest_dai_repayment': maximum['tx_hash'] == e['tx_hash'] and maximum['logIndex'] == e['logIndex'],
             'largest_dai_repayment': {k: maximum[k] for k in ('tx_hash', 'logIndex', 'blockNumber', 'repayAmount', 'repay_usd_estimate')},
             'receipt_sample': checks, 'report_comparison': comparison}
    summary = {'provenance': proof, **setup, 'valuation_note': NOTE, 'valuation_formula': 'repayAmount * oracle_price_raw / 10^36',
        'market_totals': [{**m, **totals([e for e in events if e['repaid_market'] == m['ctoken']])} for m in setup['markets']],
        'dai_related': related, 'dai_repaid': repaid, 'total': total, 'cross_checks': cross,
        'scope': 'Compound v2 markets listed at UTC-window first block; DAI-related means either repaid or collateral market is cDAI'}
    # Output numeric values are strings, including all nested structures.
    def validate(value):
        assert not isinstance(value, (int, float)) or isinstance(value, bool), 'JSON number not string'
        if isinstance(value, dict):
            for child in value.values():
                validate(child)
        elif isinstance(value, list):
            for child in value:
                validate(child)
    for name, obj in [('events', {'provenance': proof, 'events': events}),
                      ('accounts', {'provenance': proof, 'accounts': accounts}), ('summary', summary)]:
        require_evidence(obj, name)
        validate(obj)
        save(DIR / (name + '.json'), obj)
    print(json.dumps({'total': total, 'dai_related': related, 'cross_checks': cross}, ensure_ascii=True), flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        DIR.mkdir(parents=True, exist_ok=True)
        failure = {'error': redact(exc), 'rpc_requests_this_run': str(STATS['network_requests'])}
        save(DIR / 'failure.json', failure)
        print(json.dumps(failure, ensure_ascii=True), flush=True)
        raise SystemExit(2)
