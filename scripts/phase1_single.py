"""Phase 1: receipt evidence -> pre-liquidation oracle price -> N-1 fork.

Standard library only. Final-cache replay is offline; --rerun-fork re-executes
Foundry through the persistent, globally rate-limited read-only RPC cache.
"""
import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal, getcontext
from functools import lru_cache
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from phase0_check import ROOT, save, read_config
from rpc_cache import rpc
from rpc_transport import STATS, redact, rpc_proxy
from locate_phase0_sample import CDAI, COMPTROLLER, TOPIC, block

getcontext().prec = 80
DIR = ROOT / 'data/phase1'
SIGNATURE = 'LiquidateBorrow(address,address,uint256,address,uint256)'
STEP_DEADLINE = None


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def cast(*args):
    exe = ROOT / '.tools/foundry/cast.exe'
    run = subprocess.run([str(exe) if exe.exists() else 'cast', *args],
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30)
    if run.returncode:
        raise RuntimeError(redact(run.stdout + run.stderr))
    return run.stdout.strip()


@lru_cache(None)
def calldata(signature, *args):
    return cast('calldata', signature, *map(str, args))


def call(address, signature, n, *args):
    if STEP_DEADLINE is not None and time.monotonic() > STEP_DEADLINE:
        raise RuntimeError('25-minute step deadline reached; stop and report alternatives')
    return rpc('eth_call', [{'to': address, 'data': calldata(signature, *args)}, hex(n)])


def words(data):
    assert data.startswith('0x') and (len(data)-2) % 64 == 0, 'invalid ABI words'
    return [data[i:i+64] for i in range(2, len(data), 64)]


def address(word):
    assert len(word) == 64 and int(word[:24], 16) == 0, 'invalid address padding'
    return '0x' + word[-40:]


def usd(raw, scale=18):
    return format(Decimal(raw) / Decimal(10**scale), 'f')


def utc(raw):
    return datetime.fromtimestamp(int(raw, 16), timezone.utc).isoformat()


def select_sample():
    assert cast('keccak', SIGNATURE) == TOPIC, 'liquidation topic mismatch'
    path = DIR / 'sample.json'
    if path.exists():
        candidate = load(path)['log']
        selection = load(path)['selection']
    else:
        from phase1_discover import main as discover
        discover()
        search_path = DIR / 'search_logs.json'
        if not search_path.exists() or not load(search_path).get('complete'):
            from phase1_scan import main as scan
            scan()
        search = load(search_path)
        logs = search['logs']
        assert logs, 'No liquidation logs in bounded search'
        candidate = max(logs, key=lambda x: int(words(x['data'])[2], 16))
        selection = ('Fallback: largest verified repayAmount in the bounded 08:00–10:00 UTC search; '
            'not proven largest of the UTC day or identified as the reported $46m farmer. '
            'Historical range RPC failed; Invezz/The Block/Etherscan transaction list returned HTTP 403; '
            'accessible Decrypt report had no transaction hash. See discovery.json and search_logs.json.')
        if int(words(candidate['data'])[2],16) >= 46_000_000 * 10**18:
            selection = ('Largest cDAI liquidation by repayAmount in the fully scanned 08:00–10:00 UTC window; '
                '46m DAI size matches the reported target. Receipt-verified; no independent identification '
                'of the press-reported farmer and no whole-day maximum claim.')
    n = int(candidate['blockNumber'], 16)
    header, previous = block(n), block(n-1)
    receipt = rpc('eth_getTransactionReceipt', [candidate['transactionHash']])
    assert receipt['status'] == '0x1'
    assert receipt['transactionHash'] == candidate['transactionHash']
    assert receipt['blockHash'] == header['hash'] == candidate['blockHash']
    assert int(receipt['blockNumber'], 16) == n
    assert header['parentHash'] == previous['hash']
    assert utc(header['timestamp']).startswith('2020-11-26T')
    assert candidate['topics'] == [TOPIC] and candidate['address'].lower() == CDAI.lower()
    assert not candidate.get('removed', False)
    assert any(all(log[k] == candidate[k] for k in ('data','topics','logIndex','transactionHash','blockHash','blockNumber'))
        and log['address'].lower() == CDAI.lower() for log in receipt['logs'])
    decoded = words(candidate['data'])
    assert len(decoded) == 5
    sample = {'liquidation_transaction': receipt['transactionHash'], 'liquidation_block': n,
        'liquidation_block_hash': header['hash'], 'liquidation_timestamp_utc': utc(header['timestamp']),
        'fork_block': n-1, 'fork_block_hash': previous['hash'], 'fork_timestamp': int(previous['timestamp'],16),
        'fork_timestamp_utc': utc(previous['timestamp']), 'transaction_index': int(receipt['transactionIndex'],16),
        'liquidator': address(decoded[0]), 'borrower': address(decoded[1]), 'repayAmount': str(int(decoded[2],16)),
        'cTokenCollateral': address(decoded[3]), 'seizeTokens': str(int(decoded[4],16)),
        'receipt_status': receipt['status'], 'receipt_log_verified': True, 'log': candidate,
        'selection': selection, 'topic_signature': SIGNATURE, 'topic': TOPIC}
    save(path, sample)
    return sample


def verify_source(oracle):
    # Address comes from the historical Comptroller; the page only verifies code.
    page = ROOT / 'data/private/oracle_etherscan.html'
    page.parent.mkdir(parents=True, exist_ok=True)
    source_url = 'https://etherscan.io/address/' + oracle + '#code'
    if not page.exists():
        with urlopen(Request(source_url, headers={'User-Agent':'Mozilla/5.0'}), timeout=25) as response:
            page.write_bytes(response.read())
    text = page.read_text(encoding='utf-8')
    assert oracle.lower() in text.lower(), 'Etherscan page address mismatch'
    class SourceParser(HTMLParser):
        source = None
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if 'contract UniswapAnchoredView' in attrs.get('data-csource',''):
                self.source = attrs['data-csource']
    parser = SourceParser()
    parser.feed(text)
    source = parser.source
    assert source and 'Source Code Verified' in text and 'Exact Match' in text, 'source not verified on Etherscan'
    required = ['event PriceUpdated(string symbol, uint price);',
        'function postPrices(bytes[] calldata messages, bytes[] calldata signatures, string[] calldata symbols)',
        'return mul(1e30, priceInternal(config)) / config.baseUnit;',
        'prices[symbolHash] = reporterPrice;', 'emit PriceUpdated(symbol, reporterPrice);']
    assert all(s in source for s in required), 'unexpected oracle source; manual review needed'
    (DIR / 'oracle_source.sol').write_text(source, encoding='utf-8')
    abi = json.loads(html.unescape(re.findall(r'<pre[^>]*>(.*?)</pre>',text,re.S)[0]))
    save(DIR / 'oracle_abi.json',abi)
    topics = {x['name']: cast('keccak', x['name']+'('+','.join(i['type'] for i in x['inputs'])+')')
        for x in abi if x['type'] == 'event'}
    proof = {'source_url': source_url, 'contract': 'UniswapAnchoredView',
        'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
        'feed_signature': 'postPrices(bytes[],bytes[],string[])',
        'feed_selector': cast('sig','postPrices(bytes[],bytes[],string[])'), 'event_topics': topics,
        'accepted_event': 'PriceUpdated(string,uint256)', 'price_event_decimals': '6',
        'conversion': 'event price * 10^30 / tokenConfig.baseUnit; DAI baseUnit=10^18',
        'not_accepted_updates': ['PriceGuarded','AnchorPriceUpdated','UniswapWindowUpdated','OpenOraclePriceData.Write']}
    save(DIR / 'oracle_verification.json', proof)
    return topics


def price_evidence(sample):
    global STEP_DEADLINE
    STEP_DEADLINE = time.monotonic() + 1500
    n = sample['liquidation_block']
    oracle = address(words(call(COMPTROLLER, 'oracle()', n-1))[0])
    assert address(words(call(COMPTROLLER, 'oracle()', n))[0]) == oracle, 'oracle changed within N'
    topics = verify_source(oracle)
    dai = address(words(call(CDAI, 'underlying()', n-1))[0])
    phase0 = load(ROOT / 'data/phase0/status.json')
    assert dai == phase0['underlying'].lower(), 'underlying differs from verified Phase 0 DAI'
    assert int(call(dai, 'decimals()', n-1),16) == 18
    original = int(call(oracle,'getUnderlyingPrice(address)',n-1,CDAI),16)
    end_price = int(call(oracle,'getUnderlyingPrice(address)',n,CDAI),16)
    header = block(n)
    txs = header['transactions']
    assert txs[sample['transaction_index']] == sample['liquidation_transaction']
    before = txs[:sample['transaction_index']+1]
    # Includes every receipt through the selected transaction, not a topic-only shortcut.
    def receipt_before_deadline(tx):
        if time.monotonic() > STEP_DEADLINE:
            raise RuntimeError('25-minute receipt scan deadline reached')
        return rpc('eth_getTransactionReceipt',[tx])
    with ThreadPoolExecutor(max_workers=6) as pool:
        receipts = list(pool.map(receipt_before_deadline, before))
    logs = []
    for index, receipt in enumerate(receipts):
        assert receipt['transactionHash'] == before[index]
        assert receipt['blockHash'] == header['hash'] and int(receipt['transactionIndex'],16) == index
        logs.extend(log for log in receipt['logs'] if int(log['logIndex'],16) < int(sample['log']['logIndex'],16))
    updates, other_events = [], []
    for log in sorted(logs,key=lambda x:int(x['logIndex'],16)):
        if log['address'].lower() != oracle:
            continue
        event_name = next((name for name, topic in topics.items() if log['topics'][0] == topic), None)
        if event_name != 'PriceUpdated':
            other_events.append({'event':event_name,'log':log})
            continue
        data = bytes.fromhex(log['data'][2:])
        offset = int.from_bytes(data[:32])
        size = int.from_bytes(data[offset:offset+32])
        symbol = data[offset+32:offset+32+size].decode('ascii')
        event_price = int.from_bytes(data[32:64])
        config_words = words(call(oracle,'getTokenConfigBySymbol(string)',n-1,symbol))
        market, base_unit = address(config_words[0]), int(config_words[3],16)
        assert int(config_words[4],16) == 2, 'PriceUpdated expected REPORTER source'
        raw = event_price * 10**30 // base_unit
        prior = next((int(x['price_raw']) for x in reversed(updates) if x['symbol']==symbol),
            int(call(oracle,'getUnderlyingPrice(address)',n-1,market),16))
        updates.append({'symbol':symbol,'market':market,'base_unit':str(base_unit),'event_price_raw':str(event_price),
            'price_raw':str(raw),'price_usd':usd(event_price,6),'previous_price_raw':str(prior),'changed':raw!=prior,
            'source':{'tx_hash':log['transactionHash'],'logIndex':str(int(log['logIndex'],16))},'log':log})
    dai_updates = [x for x in updates if x['market'].lower()==CDAI.lower()]
    actual = int(dai_updates[-1]['price_raw']) if dai_updates else original
    source = dai_updates[-1]['source'] if dai_updates else {'state':'N-1 oracle state','block':str(n-1),'note':'区块内无 DAI 喂价'}
    last = {x['market']:x for x in updates}
    # Trigger only if a DAI feed transaction also changed a different asset.
    dai_txs = {x['source']['tx_hash'] for x in dai_updates}
    diagnostic = any(x['changed'] and x['market'].lower()!=CDAI.lower() and x['source']['tx_hash'] in dai_txs for x in updates)
    changed = [x for market,x in last.items() if int(x['price_raw']) != int(call(oracle,'getUnderlyingPrice(address)',n-1,market),16)]
    proof = {'oracle':oracle,'dai':dai,'reference_price_raw':str(original),'actual_price_raw':str(actual),
        'actual_price_source':source,'block_N_price_raw':str(end_price),'block_N_matches_actual':end_price==actual,
        'receipts_checked':before,'price_updates':updates,'other_oracle_events':other_events,
        'diagnostic_enabled':diagnostic,'diagnostic_prices':changed if diagnostic else [],
        'same_block_feed':bool(dai_updates)}
    if end_price != actual:
        # Fetch remaining receipts to identify all later writes that explain the end-state difference.
        later = []
        for tx in txs[sample['transaction_index']:]:
            receipt = rpc('eth_getTransactionReceipt',[tx])
            later.extend(log for log in receipt['logs'] if log['address'].lower()==oracle
                and log['topics'][0]==topics['PriceUpdated'] and int(log['logIndex'],16)>int(sample['log']['logIndex'],16))
        proof['post_liquidation_price_updates'] = later
        proof['block_N_difference_explanation'] = 'N is end-of-block state; later PriceUpdated logs are recorded separately. Pre-liquidation last write is used.'
    save(DIR / 'price_evidence.json', proof)
    STEP_DEADLINE = None
    return proof


def run_fork(sample, prices):
    env = os.environ.copy()
    env.update(PHASE1_BLOCK=str(sample['fork_block']), PHASE1_TIMESTAMP=str(sample['fork_timestamp']),
        PHASE1_COMPTROLLER=COMPTROLLER, PHASE1_CDAI=CDAI, PHASE1_BORROWER=sample['borrower'],
        PHASE1_ORACLE=prices['oracle'], PHASE1_DAI=prices['dai'],
        PHASE1_REFERENCE_PRICE=prices['reference_price_raw'], PHASE1_ACTUAL_PRICE=prices['actual_price_raw'],
        PHASE1_DIAGNOSTIC_COUNT=str(len(prices['diagnostic_prices'])))
    for i, price in enumerate(prices['diagnostic_prices']):
        env['PHASE1_MARKET_'+str(i)] = price['market']
        env['PHASE1_PRICE_'+str(i)] = price['price_raw']
    exe = ROOT / '.tools/foundry/forge.exe'
    command = [str(exe) if exe.exists() else 'forge','test','--match-contract','Phase1Test','-vv']
    path = DIR / 'fork_result.json'
    path.unlink(missing_ok=True)
    with rpc_proxy(read_config(), cached=True) as local:
        env['ETH_RPC_URL'] = local
        try:
            run = subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,
                encoding='utf-8',errors='replace',timeout=900)
        except subprocess.TimeoutExpired as exc:
            output = (exc.stdout or b'') + (exc.stderr or b'')
            save(DIR / 'forge_run.json', {'error':'900 second timeout','output':redact(output.decode(errors='replace'))})
            raise RuntimeError('Foundry timed out; see forge_run.json') from None
    save(DIR / 'forge_run.json', {'returncode':run.returncode,'output':redact(run.stdout+run.stderr)})
    assert run.returncode == 0 and path.exists(), 'Foundry failed; see data/phase1/forge_run.json'
    result = load(path)
    assert int(result['block'])==sample['fork_block'] and int(result['timestamp'])==sample['fork_timestamp']
    assert result['oracle'].lower()==prices['oracle'] and result['underlying'].lower()==prices['dai']
    for name, expected in [('reference',prices['reference_price_raw']),('real',prices['actual_price_raw']),('counterfactual',str(10**18))]:
        assert result[name]['dai_price_raw']==expected
    return result


def fingerprint():
    files = ['scripts/phase1_single.py','scripts/phase1_discover.py','scripts/phase1_scan.py',
        'scripts/phase0_check.py','scripts/rpc_cache.py','scripts/rpc_transport.py','test/Phase1.t.sol','foundry.toml']
    return hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in files)).hexdigest()


def evidence_fingerprint():
    files = ['sample.json','price_evidence.json','oracle_verification.json',
        'oracle_source.sol','oracle_abi.json','fork_result.json','forge_run.json','search_logs.json','discovery.json']
    return hashlib.sha256(b''.join((DIR/p).read_bytes() for p in files)).hexdigest()


def failure_diagnostics(sample, prices):
    """Read-only interest-size estimate, never a new experiment or parameter search."""
    n = sample['fork_block']
    rows = []
    for market in dict.fromkeys([CDAI.lower(),sample['cTokenCollateral']]):
        snapshot = [int(x,16) for x in words(call(market,'getAccountSnapshot(address)',n,sample['borrower']))]
        assert snapshot[0]==0
        rate = int(call(market,'borrowRatePerBlock()',n),16)
        accrual_block = int(call(market,'accrualBlockNumber()',n),16)
        gap = sample['liquidation_block']-accrual_block
        price = int(prices['actual_price_raw']) if market==CDAI.lower() else int(call(prices['oracle'],'getUnderlyingPrice(address)',n,market),16)
        estimated_interest = snapshot[2]*rate*gap//10**18
        rows.append({'market':market,'borrow_balance_raw':str(snapshot[2]),'borrow_rate_per_block':str(rate),
            'accrual_block':str(accrual_block),'blocks_to_N':str(gap),
            'estimated_additional_borrow_raw':str(estimated_interest),
            'estimated_additional_borrow_usd':usd(estimated_interest*price,36)})
    result = {'borrower_decode':{'borrower':sample['borrower'],'word_index':'1',
        'event_signature':SIGNATURE,'receipt_verified':True},'other_asset_updates':
        [x for x in prices['price_updates'] if x['symbol']!='DAI'],
        'interest_estimates':rows,'limitations':
        'Stored balance * N-1 borrowRatePerBlock * (N-accrualBlockNumber) / 1e18 estimates debt growth only. '
        'It excludes intra-block cash/rate changes, borrow-index rounding, reserve and collateral exchange-rate changes; '
        'it is not an exact shortfall delta. No accrual or liquidation transaction was executed.'}
    save(DIR/'failure_diagnostics.json',result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rerun-fork',action='store_true')
    args = parser.parse_args()
    DIR.mkdir(exist_ok=True)
    final = DIR / 'single_account.json'
    if final.exists() and not args.rerun_fork:
        old = load(final)
        if old.get('implementation_sha256')==fingerprint() and old.get('evidence_sha256')==evidence_fingerprint():
            record = {'result_cache_hit':True,'rpc_requests_this_run':0,'status':old['status']}
            history = load(DIR/'runs.json') if (DIR/'runs.json').exists() else []
            history.append(record)
            save(DIR/'runs.json',history)
            print(json.dumps({**old,**record},ensure_ascii=True,indent=2))
            return 0 if old['status']=='passed' else 3
    print('Step 1: verify selected liquidation receipt',flush=True)
    sample = select_sample()
    print('Step 2: verify oracle source and all preceding receipts',flush=True)
    prices = price_evidence(sample)
    print('Step 3: run N-1 Foundry groups',flush=True)
    fork = run_fork(sample,prices)
    groups = {}
    for name in ['reference','real','counterfactual']:
        group = fork[name]
        source = {'state':'N-1 oracle state','block':str(sample['fork_block'])} if name=='reference' else prices['actual_price_source'] if name=='real' else {'assumption':'DAI = $1.00; vm.mockCall'}
        groups[name] = {**group,'price_usd':usd(group['dai_price_raw']),'price_source':source,
            'liquidity_usd':usd(group['liquidity']),'shortfall_usd':usd(group['shortfall']),
            'err_interpretation':'protocol error code; no USD unit'}
    if fork['diagnostic']:
        diag=fork['diagnostic']['result']
        groups['diagnostic'] = {**diag,'diagnostic_only':True,'prices':prices['diagnostic_prices'],
            'price_usd':usd(diag['dai_price_raw']),'price_source':prices['actual_price_source'],
            'liquidity_usd':usd(diag['liquidity']),'shortfall_usd':usd(diag['shortfall'])}
    passed = fork['real']['err']=='0' and int(fork['real']['shortfall'])>0
    result = {'phase':'1','status':'passed' if passed else 'stopped_real_group_not_liquidatable',
        'sample':sample,'borrower':sample['borrower'],'oracle':prices['oracle'],'groups':groups,
        'limitations':['N-1 is an approximation: no replay of earlier N transactions or borrower activity.',
            'getAccountLiquidity does not accrue interest; liquidateBorrow accrues borrowed and collateral markets.',
            'Only DAI is overridden in formal groups; other assets retain N-1 prices.',
            '$1 is a counterfactual peg assumption, not a verified contemporaneous market price.',
            sample['selection'], 'No claim of market manipulation or full-event causation.'],
        'implementation_sha256':fingerprint(),'result_cache_hit':False,'rpc_requests_this_run':STATS['network_requests']}
    if not passed:
        try:
            result['stop_diagnostics'] = failure_diagnostics(sample,prices)
        except Exception as exc:
            result['stop_diagnostics'] = {'error':redact(exc),'interest_difference':'Could not quantify; no parameter changes attempted.'}
        result['rpc_requests_this_run'] = STATS['network_requests']
    result['evidence_sha256'] = evidence_fingerprint()
    save(final,result)
    history = load(DIR/'runs.json') if (DIR/'runs.json').exists() else []
    history.append({'result_cache_hit':False,'rpc_requests_this_run':STATS['network_requests'],
        'status':result['status'],'implementation_sha256':fingerprint(),
        'fork_result_sha256':hashlib.sha256((DIR/'fork_result.json').read_bytes()).hexdigest()})
    save(DIR/'runs.json',history)
    print(json.dumps(result,ensure_ascii=True,indent=2))
    return 0 if passed else 3


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        error = {'status':'blocked','error':redact(exc),'rpc_requests_this_run':STATS['network_requests']}
        save(DIR/'failure.json',error)
        print(json.dumps(error,ensure_ascii=True),flush=True)
        raise SystemExit(2)
