"""Independent Ethereum experiment replay; attestations only on BOT testnet 968."""
import argparse
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import tarfile
import time
from urllib.request import urlopen

from canonical import canonical_hash, load, loads
import register as registry
from phase4_manifest import RESULTS_DEFINITION, results_hash
from manifest_v2 import validate_schema, fingerprint, P3
from replay_rpc import Gateway, read_retry

ROOT = Path(__file__).resolve().parents[1]
SELF_NOTICE = '与发布者为同一地址，属于自我复现，仅作流程演示，不代表独立复现'


def classify(manifest, expected_hash, observed_hash, differences=()):
    try:
        validate_schema(manifest)
    except (ValueError, KeyError, TypeError):
        return 'NOT_COMPARABLE'
    if canonical_hash(manifest) != expected_hash:
        return 'NOT_COMPARABLE'
    if differences:
        return 'CONTEXT_DIFFERENT'
    return 'MATCH' if observed_hash == manifest['resultsHash'] else 'MISMATCH'


def attest(values, report, key):
    if report['status'] not in ('MATCH', 'MISMATCH'):
        return None
    contract, case_id, version = report['contract'], report['caseId'], report['version']
    who = registry.sender(key)
    if registry.call(values, contract, 'hasAttested(bytes32,uint256,address)(bool)', case_id, version, who) != 'false':
        raise RuntimeError('This address already attested this version; no repeat transaction')
    index = int(registry.call(values, contract, 'attestationCount(bytes32,uint256)(uint256)', case_id, version))
    matched = str(report['status'] == 'MATCH').lower()
    digest = report['observed_resultsHash']
    entry = registry.send(values, f'attest-{case_id}-v{version}-{who.lower()}',
                          [contract, 'attestReproduction(bytes32,uint256,bool,bytes32)', case_id, version, matched, digest], key)
    registry.verify_record(values, contract, entry, 'getAttestation(bytes32,uint256,uint256)', [case_id, version, index],
                           'f((address,bool,bytes32,uint256,uint256))', [who, matched, digest],
                           'ReproductionAttested(bytes32,uint256,address,bool)', case_id, 'f(uint256,address,bool)', [version, who, matched])
    if registry.call(values, contract, 'hasAttested(bytes32,uint256,address)(bool)', case_id, version, who) != 'true':
        raise RuntimeError('Attestation membership readback failed')
    return entry['transactionHash']


def clean_directory(path, boundary):
    path, boundary = Path(path).resolve(), Path(boundary).resolve()
    if path == boundary or boundary not in path.parents:
        raise ValueError('Cleanup target outside isolated directory')
    if path.exists():
        shutil.rmtree(path)


def retry_read(action, label):
    """Retry transient transport failures only; never retry a transaction or alter results."""
    return read_retry(action, lambda n, delay: print(json.dumps(
        {'operation': label, 'network_retry': n, 'backoff_seconds': delay}), flush=True))


def checkout(commit, work):
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Invalid script_commit')
    if work.exists():
        raise ValueError('Refusing to overwrite producer directory')
    work.mkdir()
    # Git archive preserves exact blob bytes and never materializes old RPC/Phase 3 caches.
    raw = subprocess.check_output(['git', '-c', 'core.autocrlf=false', 'archive', commit, 'scripts', 'test', 'docs',
                                   'foundry.toml', 'data/phase2', 'data/phase0', 'data/phase1'], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archive.extractall(work, filter='data')
    for path in (work / 'data/phase2').glob('*.json'):
        if not path.name.endswith(('_verification.json', '_abi.json')):
            path.unlink()


def tools_into(work):
    (work / '.tools/foundry').mkdir(parents=True, exist_ok=True)
    for relative in ('solc.exe', 'foundry/forge.exe', 'foundry/cast.exe'):
        shutil.copy2(ROOT / '.tools' / relative, work / '.tools' / relative)


def worker(work, manifest_path, output, level):
    """Harness calls unchanged Phase 3 functions; historical caches stay inside worktree."""
    sys.path.insert(0, str(work / 'scripts'))
    import rpc_cache
    import rpc_transport
    import phase2_events as p2
    if level != 'phase2':
        import phase3_batch as p3
    from decimal import Decimal
    manifest = load(manifest_path)
    base = work.parent
    cache = work / 'data/rpc'
    if Path(os.environ['RPC_CACHE_DIR']).resolve() != cache.resolve():
        raise ValueError('Historical cache must use isolated worktree/data/rpc')
    # No module monkeypatching and no source rewriting.
    (work / '.env').write_text('ETH_RPC_URL=' + os.environ['REPLAY_ETH_RPC_URL'] + '\n', encoding='utf-8')
    result = {'producer_transport_requests': 0, 'complete': False}
    from datetime import datetime, timezone
    proof = {'mode': 'LIVE', 'source': 'Ethereum mainnet archive RPC', 'capturedAt': datetime.now(timezone.utc).isoformat()}
    try:
        if rpc_cache.rpc('eth_chainId', [], use_cache=False) != '0x1':
            raise ValueError('Ethereum RPC chain ID is not 1')
        if level == 'phase2':
            # Old Phase 2 requires Phase 1 cDAI window cache. Acquire it from RPC afresh.
            for n in range(11332824, 11333317):
                h = rpc_cache.rpc('eth_getBlockByNumber', [hex(n), False])
                rpc_cache.rpc('eth_getLogs', [{'address': p2.CDAI, 'topics': [p2.TOPIC], 'blockHash': h['hash']}])
            sys.argv = ['phase2_events.py']
            p2.main()
            for name in ('accounts.json', 'events.json'):
                registry.save(base / 'inputs' / name, load(work / 'data/phase2' / name))
            result['complete'] = True
            return
        accounts = load(base / 'inputs/accounts.json')
        events = load(base / 'inputs/events.json')
        index = {(e['tx_hash'], e['logIndex']): e for e in events['events']}
        chosen = sorted([a for a in accounts['accounts'] if a['top20']], key=lambda a: int(a['rank']))
        if [a['borrower'] for a in chosen] != [a['borrower'] for a in manifest['accounts']]:
            raise ValueError('Manifest account selection differs')
        samples = {}
        for account, expected in zip(chosen, manifest['accounts']):
            e = min((index[(r['tx_hash'], r['logIndex'])] for r in account['events']), key=lambda e: (int(e['blockNumber']), int(e['logIndex'])))
            if e['blockNumber'] != expected['sampleBlock'] or int(e['blockNumber']) - 1 != int(expected['forkBlock']):
                raise ValueError('Manifest sample/fork block differs')
            samples[account['borrower']] = e
        max_indexes = {}
        for e in samples.values():
            max_indexes[e['blockNumber']] = max(max_indexes.get(e['blockNumber'], 0), int(e['transactionIndex']))
        rows = []
        for account in chosen:
            e = samples[account['borrower']]
            checkpoint = base / 'checkpoints' / (account['borrower'] + '.json')
            binding = canonical_hash({'manifest': canonical_hash(manifest), 'account': account, 'event': e})
            if checkpoint.exists():
                saved = load(checkpoint)
                if saved['binding'] != binding or canonical_hash(saved['row']) != saved['rowHash']:
                    raise ValueError('Checkpoint integrity or input binding failed')
                rows.append(saved['row'])
                print(json.dumps({'rank': account['rank'], 'stage': 'resumed'}), flush=True)
                continue
            print(json.dumps({'rank': account['rank'], 'stage': 'started', 'upstream_requests': rpc_transport.STATS['network_requests']}), flush=True)
            # Verify each selected liquidation directly, including the non-DAI sample.
            receipt = rpc_cache.rpc('eth_getTransactionReceipt', [e['tx_hash']])
            keys = ('address', 'topics', 'data', 'blockNumber', 'blockHash', 'transactionHash', 'transactionIndex', 'logIndex')
            if receipt['status'] != '0x1' or not any(all(log[k] == e['raw_log'][k] for k in keys) for log in receipt['logs']):
                raise ValueError('Frozen sample event differs from Ethereum RPC')
            row = {'provenance': proof, 'borrower': account['borrower'], 'rank': account['rank'],
                   'sample_event': {k: e[k] for k in ('tx_hash', 'blockNumber', 'blockHash', 'transactionIndex', 'logIndex')},
                   'groups': {}, 'critical_price': None, 'status': 'not_applicable',
                   'repay_usd_estimate_total': account['repay_usd_estimate_total']}
            if account['dai_related']:
                folder = work / 'data/phase3/accounts' / account['borrower']
                prices = p3.price_evidence(e, max_indexes[e['blockNumber']], proof)
                fork = p3.run_fork(e, prices, folder, proof)
                groups = {'reference': p3.enrich(fork['reference'], {'state': 'N-1 oracle state', 'block': str(int(e['blockNumber']) - 1)}),
                          'real': p3.enrich(fork['real'], prices['actual_price_source'])}
                for label, group in zip(p3.PRICES, fork['sensitivity']):
                    if group['dai_price_raw'] != str(int(Decimal(label) * 10**18)):
                        raise ValueError('Invalid sensitivity price')
                    groups[label] = p3.enrich(group, {'assumption': 'DAI = $' + label + '; vm.mockCall'})
                critical = fork['critical_price']
                critical['derived'] = True
                critical['price_usd'] = p3.usd(critical['price_raw']) if critical['price_raw'] else None
                for side in ('below', 'above'):
                    if side in critical:
                        critical[side] = p3.enrich(critical[side], {'assumption': 'derived critical price ' + side + ' by $0.0001; vm.mockCall'})
                row.update(groups=groups, critical_price=critical,
                           status='passed' if groups['real']['err'] == '0' and int(groups['real']['shortfall']) > 0 else 'real_not_reproduced')
            rows.append(row)
            p3.write(work / 'data/phase3/accounts' / account['borrower'] / 'experiment.json', row)
            registry.save(checkpoint, {'binding': binding, 'rowHash': canonical_hash(row), 'row': row})
            print(json.dumps({'rank': account['rank'], 'status': row['status'], 'upstream_requests': rpc_transport.STATS['network_requests']}), flush=True)
        p3.write(work / 'data/phase3/experiments.json', {'provenance': proof, 'experiments': rows})
        p3.write(work / 'data/phase3/sensitivity.json', p3.aggregate(rows, proof))
        result.update(complete=True, observed_resultsHash=results_hash(load(work / 'data/phase3/experiments.json'), load(work / 'data/phase3/sensitivity.json')))
    except Exception as exc:
        result['execution_error'] = rpc_transport.redact(exc)
        # A sanitized error is enough; tracebacks from historical clients may contain URLs.
        print(json.dumps({'execution_error': result['execution_error']}), flush=True)
    finally:
        # Keep partial results and redacted failure diagnostics even when a provider fails.
        if (work / 'data/phase3').exists():
            shutil.copytree(work / 'data/phase3', output.parent / 'generated-phase3', dirs_exist_ok=True)
        result.update(producer_transport_requests=rpc_transport.STATS['network_requests'], cache_hits=rpc_transport.STATS['cache_hits'])
        registry.save(output, result)


def reproduce(args):
    from replay_session import run
    run(args, sys.modules[__name__])


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--worker':
        worker(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--network', choices=['testnet', 'mainnet'], required=True)
    parser.add_argument('--case', default='compound-2020-11-26-dai')
    parser.add_argument('--version', type=int)
    parser.add_argument('--level', choices=['full', 'quick'], default='full')
    parser.add_argument('--attest', action='store_true')
    parser.add_argument('--eth-rpc-env', default='ETH_RPC_URL')
    parser.add_argument('--resume', help='Retained temporary session directory')
    parser.add_argument('--probe-rpc', action='store_true', help='Read-only historical eth_call preflight')
    args = parser.parse_args()
    if args.probe_rpc:
        registry.network(args.network)
        if not re.fullmatch(r'ETH_RPC_URL(?:_[A-Z0-9_]+)?', args.eth_rpc_env):
            raise ValueError('Invalid Ethereum RPC variable name')
        values = registry.config((args.eth_rpc_env,))
        result = Gateway(values[args.eth_rpc_env]).preflight()
        registry.save(ROOT / 'deployments/reproduction-rpc-preflight-v2.json', result)
        print(json.dumps(result, indent=2))
    else:
        reproduce(args)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR:', registry.redact(exc))
        raise SystemExit(1) from None
