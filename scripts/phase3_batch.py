"""Resumable, standard-library-only Phase 3; immutable N-1 per borrower."""
import argparse
import hashlib
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal

from phase0_check import ROOT, read_config, save
from phase1_single import load, cast, call, words, address, usd
from locate_phase0_sample import CDAI, COMPTROLLER, block
from phase2_contract import require_evidence, SOURCE
from rpc_cache import rpc, RpcError
from rpc_transport import STATS, redact, rpc_proxy

DIR = ROOT / 'data/phase3'
LIMITATIONS = ['单变量假设：正式组只改 DAI 价格，其他资产保持 N−1。',
    'N−1 是近似状态，没有重放区块 N 的早先交易或账户操作。',
    'getAccountLiquidity 不计提利息；真实清算会计提借款和抵押市场利息，缺口不等于交易内精确缺口。',
    '只用首次清算，清算次数按全部事件计。', '临界价格是推导值，固定其他价格并验证 ±0.0001 美元符号翻转。',
    '1.00 美元是锚定价格，不是当时的市场价。', '不据此认定操纵或整个事件的单一原因。']
PRICES = ['1.00', '1.05', '1.10', '1.20', '1.30']


def reject_mock(value):
    if isinstance(value, dict):
        if value.get('mode') == 'UI_MOCK':
            raise ValueError('UI_MOCK cannot be evidence')
        for child in value.values():
            reject_mock(child)
    elif isinstance(value, list):
        for child in value:
            reject_mock(child)


def checked_load(path):
    value = load(path)
    reject_mock(value)
    return value


def write(path, value):
    reject_mock(value)
    def validate(v):
        if isinstance(v, dict):
            for child in v.values(): validate(child)
        elif isinstance(v, list):
            for child in v: validate(child)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            raise ValueError('Numeric JSON values must be strings')
    validate(value)
    for attempt in range(20):
        try:
            save(path, value)
            return
        except PermissionError:
            if attempt == 19: raise
            time.sleep(0.05)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def implementation():
    paths = ['scripts/phase3_batch.py', 'test/Phase3.t.sol', 'test/Phase1.t.sol',
             'scripts/rpc_cache.py', 'scripts/rpc_transport.py', 'scripts/phase1_single.py',
             'scripts/phase0_check.py', 'scripts/phase2_contract.py', 'foundry.toml']
    return hashlib.sha256(b''.join((ROOT / p).read_bytes() for p in paths)).hexdigest()


def receipts(n, max_index, proof):
    path = DIR / 'receipts' / (str(n) + '.json')
    h = block(n)
    if path.exists():
        old = checked_load(path)
        assert old['block_hash'] == h['hash'] and int(old['through_index']) >= max_index
        return old['receipts']
    started = time.monotonic()
    fallback = None
    attempt_path = path.with_name(str(n) + '_fallback.json')
    try:
        if attempt_path.exists():
            raise RpcError(checked_load(attempt_path)['error'])
        rows = rpc('eth_getBlockReceipts', [hex(n)])
        assert isinstance(rows, list) and len(rows) == len(h['transactions'])
        method = 'eth_getBlockReceipts'
    except RpcError as exc:
        # Persist the failed capability attempt per block, so interrupted fallback never retries it.
        fallback = redact(exc)
        write(attempt_path, {'provenance': proof, 'error': fallback})
        rows = None
        method = 'eth_getTransactionReceipt'
    if rows is None:
        def fetch(tx):
            if time.monotonic() - started > 1500:
                raise RuntimeError('25-minute receipt deadline reached; stop and report')
            return rpc('eth_getTransactionReceipt', [tx])
        with ThreadPoolExecutor(max_workers=8) as pool:
            rows = list(pool.map(fetch, h['transactions'][:max_index + 1]))
    rows.sort(key=lambda r: int(r['transactionIndex'], 16))
    for i, r in enumerate(rows):
        assert int(r['transactionIndex'], 16) == i
        assert r['transactionHash'] == h['transactions'][i]
        assert r['blockHash'] == h['hash'] and int(r['blockNumber'], 16) == n
        for log in r['logs']:
            assert log['transactionHash'] == r['transactionHash'] and log['blockHash'] == h['hash']
            assert int(log['transactionIndex'], 16) == i and int(log['blockNumber'], 16) == n
            assert not log.get('removed', False)
    write(path, {'provenance': proof, 'block_hash': h['hash'], 'through_index': str(len(rows)-1),
                 'method': method, 'fallback_reason': fallback, 'receipts': rows})
    return rows


def price_evidence(e, max_index, proof):
    n = int(e['blockNumber'])
    oracle = address(words(call(COMPTROLLER, 'oracle()', n-1))[0])
    verified = checked_load(ROOT / 'data/phase1/oracle_verification.json')
    assert oracle in verified['source_url'].lower(), 'Unverified oracle implementation'
    assert address(words(call(COMPTROLLER, 'oracle()', n))[0]) == oracle
    topic = cast('keccak', 'PriceUpdated(string,uint256)')
    assert topic == verified['event_topics']['PriceUpdated']
    dai = address(words(call(CDAI, 'underlying()', n-1))[0])
    assert dai == checked_load(ROOT / 'data/phase0/status.json')['underlying'].lower()
    assert int(call(dai, 'decimals()', n-1), 16) == 18
    original = int(call(oracle, 'getUnderlyingPrice(address)', n-1, CDAI), 16)
    rows = receipts(n, max_index, proof)
    selected = next(r for r in rows if r['transactionHash'] == e['tx_hash'])
    assert selected['status'] == '0x1'
    keys = ('address','topics','data','blockNumber','blockHash','transactionHash','transactionIndex','logIndex')
    assert any(all(log[k] == e['raw_log'][k] for k in keys) for log in selected['logs'])
    logs = [log for r in rows for log in r['logs']
            if (int(log['transactionIndex'],16), int(log['logIndex'],16)) < (int(e['transactionIndex']), int(e['logIndex']))
            and log['address'].lower() == oracle and log['topics'] == [topic]]
    updates = []
    for log in sorted(logs, key=lambda l: int(l['logIndex'],16)):
        data = bytes.fromhex(log['data'][2:]); offset = int.from_bytes(data[:32]); size = int.from_bytes(data[offset:offset+32])
        symbol = data[offset+32:offset+32+size].decode('ascii')
        event_price = int.from_bytes(data[32:64])
        config = words(call(oracle, 'getTokenConfigBySymbol(string)', n-1, symbol))
        market, base = address(config[0]), int(config[3],16)
        assert int(config[4],16) == 2
        if market == CDAI.lower(): assert base == 10**18 and symbol == 'DAI'
        previous = int(call(oracle, 'getUnderlyingPrice(address)', n-1, market),16)
        raw = event_price * 10**30 // base
        updates.append({'symbol':symbol,'market':market,'base_unit':str(base),'event_price_raw':str(event_price),
            'price_raw':str(raw),'price_usd':usd(event_price,6),'reference_price_raw':str(previous),
            'changed_from_reference':raw != previous,
            'source':{'tx_hash':log['transactionHash'],'logIndex':str(int(log['logIndex'],16))},'log':log})
    dais = [u for u in updates if u['market'] == CDAI.lower()]
    actual = dais[-1]['price_raw'] if dais else str(original)
    source = dais[-1]['source'] if dais else {'state':'N-1 oracle state','block':str(n-1),'note':'区块内无喂价'}
    last = {u['market']:u for u in updates}
    other = [u for u in updates if u['market'] != CDAI.lower()]
    diagnostic = list(last.values()) if other else []
    return {'provenance':proof,'oracle':oracle,'dai':dai,'reference_price_raw':str(original),
        'actual_price_raw':actual,'actual_price_source':source,'price_updates':updates,
        'other_asset_updates':other,'diagnostic_prices':diagnostic,
        'receipt_bundle':'data/phase3/receipts/'+str(n)+'.json'}


def run_fork(e, prices, folder, proof):
    n = int(e['blockNumber']) - 1
    env = os.environ.copy()
    env.update(PHASE1_BLOCK=str(n), PHASE1_TIMESTAMP=str(int(block(n)['timestamp'],16)),
        PHASE1_COMPTROLLER=COMPTROLLER, PHASE1_CDAI=CDAI, PHASE1_BORROWER=e['borrower'],
        PHASE1_ORACLE=prices['oracle'], PHASE1_DAI=prices['dai'], PHASE1_REFERENCE_PRICE=prices['reference_price_raw'],
        PHASE1_ACTUAL_PRICE=prices['actual_price_raw'], PHASE1_DIAGNOSTIC_COUNT=str(len(prices['diagnostic_prices'])),
        PHASE3_OUTPUT=(folder / 'fork_result.json').relative_to(ROOT).as_posix())
    for i, item in enumerate(prices['diagnostic_prices']):
        env['PHASE1_MARKET_'+str(i)] = item['market']; env['PHASE1_PRICE_'+str(i)] = item['price_raw']
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / 'fork_result.json'
    path.unlink(missing_ok=True)
    with rpc_proxy(read_config(), cached=True) as local:
        env['ETH_RPC_URL'] = local
        try:
            run = subprocess.run([str(ROOT / '.tools/foundry/forge.exe'), 'test', '--match-contract', '^Phase3Test$',
                '--match-test', 'testBatchAccount', '-vv'], cwd=ROOT,env=env,capture_output=True,text=True,
                encoding='utf-8',errors='replace',timeout=1500)
        except subprocess.TimeoutExpired:
            raise RuntimeError('25-minute forge deadline reached; stop and report') from None
    write(folder / 'forge_run.json', {'provenance':proof,'returncode':str(run.returncode),'output':redact(run.stdout+run.stderr)})
    assert run.returncode == 0 and path.exists(), 'Foundry failed: '+str(folder / 'forge_run.json')
    result = checked_load(path)
    assert result['block'] == str(n) and result['oracle'].lower() == prices['oracle']
    result['provenance'] = proof
    write(path, result)
    return result


def enrich(group, source):
    return {**group,'price_usd':usd(group['dai_price_raw']),'price_source':source,
        'liquidity_usd':usd(group['liquidity']),'shortfall_usd':usd(group['shortfall']),
        'err_interpretation':'protocol error code; no USD unit'}


def regression(row, phase1):
    if row['borrower'] != phase1['borrower']: return
    assert row['sample_event']['tx_hash'] == phase1['sample']['liquidation_transaction'], 'Phase 1 sample mismatch; STOP'
    assert row['sample_event']['logIndex'] == str(int(phase1['sample']['log']['logIndex'],16))
    for name, key in [('reference','reference'),('real','real'),('counterfactual','1.00')]:
        assert row['groups'][key] == phase1['groups'][name], 'Phase 1 regression mismatch: '+name+'; STOP'
    assert row['status'] == phase1['status'] and row['oracle'] == phase1['oracle']


def aggregate(rows, proof):
    passed = [r for r in rows if r['status'] == 'passed']
    output = []
    for label in PRICES + ['real']:
        eligible = [r for r in passed if int(r['groups'][label]['shortfall']) > 0]
        output.append({'group':label,'price_usd':label if label != 'real' else None,
            'liquidatable_accounts':str(len(eligible)),
            'repay_usd_estimate_total':format(sum((Decimal(r['repay_usd_estimate_total']) for r in eligible),Decimal(0)),'f'),
            'shortfall_total_raw':str(sum(int(r['groups'][label]['shortfall']) for r in eligible)),
            'shortfall_total_usd':usd(sum(int(r['groups'][label]['shortfall']) for r in eligible)),
            'included_accounts':str(len(passed))})
    return {'provenance':proof,'valuation_note':'N−1 排序估值；合计这些账户全天偿还估值，不是该价格下模拟清算额或损失。',
            'selection':'passed accounts only; diagnostic_only excluded','rows':output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache-only',action='store_true')
    parser.add_argument('--rerun-fork',action='store_true')
    args = parser.parse_args()
    if args.cache_only:
        import rpc_cache
        def deny(*a, **kw): raise RuntimeError('Cache-only: network access forbidden')
        rpc_cache.exchange = deny
    started = time.monotonic()
    origin_path = DIR / 'origin.json'
    if not origin_path.exists():
        write(origin_path, {'provenance':{'mode':'LIVE','source':SOURCE,'capturedAt':datetime.now(timezone.utc).isoformat()}})
    proof = checked_load(origin_path)['provenance'].copy()
    if args.cache_only:
        proof['mode'] = 'FROZEN'
    account_doc = checked_load(ROOT / 'data/phase2/accounts.json')
    event_doc = checked_load(ROOT / 'data/phase2/events.json')
    require_evidence(account_doc,'accounts'); require_evidence(event_doc,'events')
    phase1 = checked_load(ROOT / 'data/phase1/single_account.json')
    accounts = [a for a in account_doc['accounts'] if a['top20']]
    index = {(e['tx_hash'],e['logIndex']):e for e in event_doc['events']}
    samples = {a['borrower']:min([index[(r['tx_hash'],r['logIndex'])] for r in a['events']],
        key=lambda e:(int(e['blockNumber']),int(e['logIndex']))) for a in accounts}
    assert phase1['borrower'] in samples
    accounts.sort(key=lambda a:(a['borrower'] != phase1['borrower'], int(a['rank'])))
    max_indexes = {}
    for a in accounts:
        e = samples[a['borrower']]
        if a['dai_related']: max_indexes[e['blockNumber']] = max(max_indexes.get(e['blockNumber'],0),int(e['transactionIndex']))
    code_hash = implementation()
    rows, cache_hits = [], 0
    run = {'provenance':proof,'started_utc':datetime.now(timezone.utc).isoformat(),'cache_only':args.cache_only,'status':'running'}
    try:
        for a in accounts:
            e = samples[a['borrower']]
            folder = DIR / 'accounts' / a['borrower']
            path = folder / 'experiment.json'
            fingerprint = digest({'code':code_hash,'account':{k:v for k,v in a.items() if k != 'status'},
                'event':e,'phase1':phase1,'oracle_verification':checked_load(ROOT/'data/phase1/oracle_verification.json')})
            if path.exists() and not args.rerun_fork:
                row = checked_load(path)
                if row.get('input_sha256') == fingerprint:
                    assert row['result_sha256'] == digest({k:v for k,v in row.items() if k != 'result_sha256'})
                    regression(row,phase1); rows.append(row); cache_hits += 1; continue
            print(json.dumps({'rank':a['rank'],'borrower':a['borrower'],'stage':'started','rpc_requests':str(STATS['network_requests'])}),flush=True)
            row = {'provenance':proof,'borrower':a['borrower'],'rank':a['rank'],'sample_event':
                {k:e[k] for k in ('tx_hash','blockNumber','blockHash','transactionIndex','logIndex')},
                'liquidation_count':a['liquidation_count'],'repay_usd_estimate_total':a['repay_usd_estimate_total'],
                'input_sha256':fingerprint,'limitations':LIMITATIONS,'groups':{},'critical_price':None}
            if not a['dai_related']:
                row.update(status='not_applicable',reason='与 DAI 无关')
            else:
                prices = price_evidence(e,max_indexes[e['blockNumber']],proof)
                write(folder/'price_evidence.json',prices)
                fork = run_fork(e,prices,folder,proof)
                groups = {'reference':enrich(fork['reference'],{'state':'N-1 oracle state','block':str(int(e['blockNumber'])-1)}),
                          'real':enrich(fork['real'],prices['actual_price_source'])}
                for label,g in zip(PRICES,fork['sensitivity']):
                    assert g['dai_price_raw'] == str(int(Decimal(label)*10**18))
                    groups[label] = enrich(g,{'assumption':'DAI = $'+label+'; vm.mockCall'})
                assert groups['reference']['dai_price_raw'] == prices['reference_price_raw']
                assert groups['real']['dai_price_raw'] == prices['actual_price_raw']
                passed = groups['real']['err'] == '0' and int(groups['real']['shortfall']) > 0
                critical = fork['critical_price']; critical['derived'] = True
                critical['price_usd'] = usd(critical['price_raw']) if critical['price_raw'] else None
                for side in ('below', 'above'):
                    if side in critical:
                        critical[side] = enrich(critical[side], {'assumption':'derived critical price '+side+' by $0.0001; vm.mockCall'})
                diagnostic = fork['diagnostic']
                if diagnostic:
                    diagnostic['prices'] = prices['diagnostic_prices']
                    diagnostic['result'] = enrich(diagnostic['result'],prices['actual_price_source'])
                same = [index[(r['tx_hash'],r['logIndex'])] for r in a['events'] if index[(r['tx_hash'],r['logIndex'])]['blockNumber'] == e['blockNumber']]
                row.update(status='passed' if passed else 'real_not_reproduced',oracle=prices['oracle'],groups=groups,
                    critical_price=critical,price_evidence=prices,diagnostic=diagnostic,
                    failure_diagnostics={'other_asset_updates':prices['other_asset_updates'],
                        'same_block_liquidation_count':str(len(same)),'repeated_liquidation_same_block':len(same)>1,
                        'interest_explanation':LIMITATIONS[2],'state_explanation':LIMITATIONS[1]})
                regression(row,phase1)
            row['result_sha256'] = digest(row)
            write(path,row); rows.append(row)
            print(json.dumps({'rank':a['rank'],'status':row['status'],'rpc_requests':str(STATS['network_requests'])}),flush=True)
        proof = {**proof,'mode':'LIVE' if STATS['network_requests'] else 'FROZEN'}
        output = {'provenance':proof,'phase1_regression':'exact_match','regression_scope':'same sample, oracle, status and all fields of reference/real/counterfactual groups',
            'rpc_requests_this_run':str(STATS['network_requests']),
            'valuation_note':'N−1 排序估值；每账户全天偿还额，不是模拟清算金额或损失。',
            'implementation_sha256':code_hash,'limitations':LIMITATIONS,'experiments':sorted(rows,key=lambda r:int(r['rank']))}
        write(DIR/'experiments.json',output)
        write(DIR/'sensitivity.json',aggregate(rows,proof))
        # Explicitly offline Phase 2 regeneration, including account acceptance status.
        refresh = subprocess.run([os.sys.executable,'scripts/phase2_events.py','--cache-only'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=180)
        if refresh.returncode: raise RuntimeError('Phase 2 offline regeneration failed: '+redact(refresh.stdout[-1800:]))
        assert checked_load(ROOT/'data/phase2/runs.json')[-1]['rpc_requests_this_run'] == '0'
        run['status'] = 'passed'
    except Exception as exc:
        run.update(status='failed',error=redact(exc))
        raise
    finally:
        run.update(provenance={**proof,'mode':'LIVE' if STATS['network_requests'] else 'FROZEN'},
            rpc_requests_this_run=str(STATS['network_requests']),cache_hits=str(STATS['cache_hits']),
            account_result_cache_hits=str(cache_hits),elapsed_seconds=format(time.monotonic()-started,'.3f'))
        history = checked_load(DIR/'runs.json')['runs'] if (DIR/'runs.json').exists() else []
        write(DIR/'runs.json',{'provenance':run['provenance'],'runs':history+[run]})
        print(json.dumps(run,ensure_ascii=True),flush=True)
    from phase3_report import main as report
    report()


if __name__ == '__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'error':redact(exc)},ensure_ascii=True),flush=True)
        raise SystemExit(2)
