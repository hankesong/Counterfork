"""Persistent isolated session orchestration for reproduce.py."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from canonical import canonical_hash, load, loads
from manifest_v2 import fingerprint
from replay_rpc import Gateway, read_retry
import register as registry

ROOT = Path(__file__).resolve().parents[1]


def tool_versions():
    solc = subprocess.check_output([str(ROOT / '.tools/solc.exe'), '--version'], text=True)
    return {'python': platform.python_version(), **{name: registry.run(name, '--version') for name in ('cast', 'forge')},
            'solc': re.search(r'Version: (\d+\.\d+\.\d+\+commit\.[0-9a-f]+)', solc).group(1)}


def verify_producer(work, producer):
    fp = producer['codeFingerprint']
    blobs = [(work / p).read_bytes() for p in fp['filesInOrder']]
    if hashlib.sha256(b''.join(blobs)).hexdigest() != fp['sha256'] or any(
            hashlib.sha256(b).hexdigest() != fp['fileSha256'][p] for p, b in zip(fp['filesInOrder'], blobs)):
        raise ValueError('Producer source integrity failed')


def run(args, api):
    values = registry.network(args.network)
    registry.chain(values)
    official = load(registry.OFFICIAL)
    contract = official['contract']
    case_id = registry.run('cast', 'keccak', args.case)
    version = args.version or int(registry.call(values, contract, 'latestVersion(bytes32)(uint256)', case_id))
    signature = 'getInvestigation(bytes32,uint256)((address,uint256,uint256,uint256,bytes32,string,uint256,uint256))'
    fields = registry.call(values, contract, signature, case_id, version, decoded=True)[0]
    expected_hash, uri = fields[4:6]
    output = ROOT / 'deployments' / f'reproduction-{args.level}-v{version}.json'
    if output.exists() and not args.resume:
        raise RuntimeError('Report exists; use --resume with its session directory for an incomplete run')
    if output.exists() and json.loads(output.read_text(encoding='utf-8')).get('status') in ('MATCH', 'MISMATCH'):
        raise RuntimeError('Completed report preserved; do not replay or attest twice')
    started = time.monotonic()
    base = None
    gateway = None
    previous_elapsed = 0
    report = {'status': 'NOT_COMPARABLE', 'case': args.case, 'caseId': case_id, 'version': version,
              'contract': contract, 'chain_id': 968, 'level': args.level, 'chain_manifestHash': expected_hash,
              'manifestURI': uri, 'expected_resultsHash': None, 'observed_resultsHash': None,
              'network_requests': 0, 'retries': 0, 'attestation_transaction': None}
    try:
        if not re.fullmatch(r'https://raw\.githubusercontent\.com/hankesong/Counterfork/[0-9a-f]{40}/data/phase4/manifest(?:-v2)?\.json', uri):
            raise ValueError('Unsupported manifest URI')
        def download():
            with urlopen(uri, timeout=45) as response:
                return loads(response.read().decode('utf-8'))
        download_retries = []
        manifest = read_retry(download, lambda n, delay: download_retries.append(n))
        report['manifest_download_retries'] = len(download_retries)
        report['downloaded_manifestHash'] = canonical_hash(manifest)
        if api.classify(manifest, expected_hash, None) == 'NOT_COMPARABLE':
            raise ValueError('Manifest hash or schema validation failed')
        if manifest.get('schemaVersion') != '2':
            raise ValueError('Replay requires v2 producerCommits; v1 has no valid producer contract')
        if manifest['caseId'] != {'text': args.case, 'hash': case_id} or [str(x) for x in fields[1:4]] != [manifest['targetChainId'], manifest['fromBlock'], manifest['toBlock']]:
            raise ValueError('Manifest does not match registered investigation fields')
        artifact_commit = uri.split('/')[5]
        for item in manifest['files']:
            if not re.fullmatch(r'data/phase[234]/[A-Za-z_]+\.json', item['path']):
                raise ValueError('Invalid evidence path')
            if canonical_hash(loads(registry.run('git', 'show', artifact_commit + ':' + item['path'], cwd=ROOT))) != item['hash']:
                raise ValueError('Frozen artifact integrity failed: ' + item['path'])
        for producer in manifest['producerCommits'].values():
            fp = producer['codeFingerprint']
            if fingerprint(producer['commit'], fp['filesInOrder']) != fp:
                raise ValueError('Manifest producer fingerprint inconsistent with Git')
        report['producerCommits'] = manifest['producerCommits']
        report['expected_resultsHash'] = manifest['resultsHash']
        report['tools'] = tool_versions()
        report['expected_tools'] = manifest['context']['tools']
        report['context_differences'] = [] if report['tools'] == report['expected_tools'] else ['Tool versions differ']
        if report['context_differences']:
            report['status'] = 'CONTEXT_DIFFERENT'
            return
        report['status'] = None  # Execution failures are not scientific comparisons.
        if not re.fullmatch(r'ETH_RPC_URL(?:_[A-Z0-9_]+)?', args.eth_rpc_env):
            raise ValueError('--eth-rpc-env must select an ETH_RPC_URL variable')
        eth_values = registry.config((args.eth_rpc_env, 'REPRODUCER_PRIVATE_KEY'))
        eth = eth_values.get(args.eth_rpc_env)
        if not eth:
            raise ValueError('Selected Ethereum RPC environment variable is missing')
        report['rpc_url_sha256'] = hashlib.sha256(eth.encode()).hexdigest()
        report['rpc_context_policy'] = 'Endpoint excluded from context; SHA-256 recorded only.'
        key = eth_values.get('REPRODUCER_PRIVATE_KEY') or values.get('BOT_PRIVATE_KEY')
        if args.attest and not key:
            raise ValueError('Signing key required for --attest')
        report['reproducer'] = registry.sender(key) if key else None
        report['self_reproduction'] = bool(key and report['reproducer'].lower() == fields[0].lower())
        report['reproduction_notice'] = api.SELF_NOTICE if report['self_reproduction'] else 'Signer ownership independence not established'
        harness = {p: hashlib.sha256((ROOT / 'scripts' / p).read_bytes()).hexdigest()
                   for p in ('reproduce.py', 'replay_session.py', 'replay_rpc.py', 'manifest_v2.py')}
        binding = {'manifestHash': expected_hash, 'level': args.level, 'tools': report['tools'], 'harness': harness}
        if args.resume:
            base = Path(args.resume).resolve()
            temp_root = Path(tempfile.gettempdir()).resolve()
            if temp_root not in base.parents or not base.name.startswith('counterfork-reproduce-'):
                raise ValueError('Resume path must be an isolated reproduction session under TEMP')
            state = json.loads((base / 'session.json').read_text(encoding='utf-8'))
            if state['binding'] != binding or not state['fresh_cache_start']:
                raise ValueError('Resume binding differs; create a new empty session')
            previous_elapsed = state.get('elapsed_seconds', 0)
            report['resumed'] = True
        else:
            base = Path(tempfile.mkdtemp(prefix='counterfork-reproduce-'))
            state = {'binding': binding, 'fresh_cache_start': True, 'elapsed_seconds': 0}
            registry.save(base / 'session.json', state)
            registry.save(base / 'manifest.json', manifest)
            (base / 'inputs').mkdir()
            for item in manifest['quickInputs']:
                value = loads(registry.run('git', 'show', item['commit'] + ':' + item['path'], cwd=ROOT))
                if canonical_hash(value) != item['hash']:
                    raise ValueError('Quick input hash mismatch')
                registry.save(base / 'inputs' / Path(item['path']).name, value)
            stages = ['phase2', 'phase3'] if args.level == 'full' else ['phase3']
            for stage in stages:
                work = base / stage
                api.checkout(manifest['producerCommits'][stage]['commit'], work)
                api.tools_into(work)
            report['resumed'] = False
        if args.level == 'quick':
            for item in manifest['quickInputs']:
                if canonical_hash(load(base / 'inputs' / Path(item['path']).name)) != item['hash']:
                    raise ValueError('Retained quick input integrity failed')
        report['session_dir'] = str(base)
        report['isolation'] = {'fresh_cache_start': True, 'producer_source_unchanged': True,
            'gateway': 'uncached external retry proxy; whitespace heartbeat for legacy socket timeout',
            'rpc_and_proxy_cache': str(base / 'phase3/data/rpc'), 'foundry_cache': str(base / 'phase3-cache'),
            'foundry_artifacts': str(base / 'phase3-out'), 'foundry_home': str(base / 'home'),
            'foundry_no_storage_caching': True, 'session_retained_for_resume': True,
            'quick_scope': 'Frozen Phase 2 selection and weights, fresh receipts and Phase 3 experiments', 'harness': harness}
        gateway = Gateway(eth, base / 'network-stats.json')
        report['preflight'] = gateway.preflight()
        report['status'] = None
        report['execution_status'] = 'RUNNING'
        registry.save(output, report)
        print(json.dumps({'session_dir': str(base), 'preflight': report['preflight']}), flush=True)
        with gateway.serve() as local:
            stages = ['phase2', 'phase3'] if args.level == 'full' else ['phase3']
            for stage in stages:
                work = base / stage
                verify_producer(work, manifest['producerCommits'][stage])
                worker_output = base / (stage + '-result.json')
                if stage == 'phase2' and worker_output.exists() and load(worker_output).get('complete'):
                    continue
                env = registry.safe_env() | {'RPC_CACHE_DIR': str(work / 'data/rpc'), 'REPLAY_ETH_RPC_URL': local,
                    'FOUNDRY_PROFILE': 'default', 'FOUNDRY_CACHE_PATH': str(base / (stage + '-cache')),
                    'FOUNDRY_OUT': str(base / (stage + '-out')), 'FOUNDRY_NO_STORAGE_CACHING': 'true',
                    'HOME': str(base / 'home'), 'USERPROFILE': str(base / 'home')}
                (base / 'home').mkdir(exist_ok=True)
                cfg = json.loads(registry.run('forge', 'config', '--json', cwd=work, env=env))
                if (cfg.get('no_storage_caching') is not True or Path(cfg['cache_path']).resolve() != (base / (stage + '-cache')).resolve()
                        or Path(cfg['out']).resolve() != (base / (stage + '-out')).resolve()):
                    raise ValueError('Foundry cache isolation failed')
                log = ROOT / 'deployments' / f'reproduction-{args.level}-v{version}.log'
                with log.open('a', encoding='utf-8') as handle:
                    proc = subprocess.Popen([sys.executable, str(ROOT / 'scripts/reproduce.py'), '--worker', str(work),
                        str(base / 'manifest.json'), str(worker_output), 'phase2' if stage == 'phase2' else args.level],
                        cwd=base, env=env, stdout=handle, stderr=subprocess.STDOUT)
                    try:
                        proc.wait()
                    finally:
                        if proc.poll() is None:
                            proc.terminate()
                            proc.wait(timeout=30)
                verify_producer(work, manifest['producerCommits'][stage])
                completed = load(worker_output) if worker_output.exists() else {}
                if proc.returncode or not completed.get('complete'):
                    report.update(completed)
                    raise RuntimeError('Experiment incomplete; resume the retained session')
                if stage == 'phase3':
                    report.update(completed)
        if gateway.stats['network_requests'] <= report['preflight']['network_requests'] and not report['resumed']:
            raise ValueError('Fresh replay made zero experiment upstream requests')
        report.update(gateway.stats)
        report['status'] = api.classify(manifest, expected_hash, report['observed_resultsHash'])
        report['execution_status'] = 'COMPLETE'
        registry.save(output, report)
        if args.attest:
            report['attestation_transaction'] = api.attest(values, report, key)
    except Exception as exc:
        report['error'] = registry.redact(exc)
        if report['status'] is None:
            report['execution_status'] = 'FAILED'
        raise
    finally:
        report['elapsed_seconds'] = round(previous_elapsed + time.monotonic() - started, 3)
        if gateway:
            report.update(gateway.stats)
            report['rpc_retries'] = gateway.stats['retries']
            report['retries'] = gateway.stats['retries'] + report.get('manifest_download_retries', 0)
        if base and (base / 'session.json').exists():
            state = json.loads((base / 'session.json').read_text(encoding='utf-8'))
            state['elapsed_seconds'] = report['elapsed_seconds']
            registry.save(base / 'session.json', state)
            if (base / 'generated-phase3').exists():
                shutil.copytree(base / 'generated-phase3', ROOT / 'deployments' / f'reproduction-{args.level}-v{version}-evidence', dirs_exist_ok=True)
            report['session_dir'] = str(base)
        registry.save(output, report)
        print(json.dumps(report, ensure_ascii=True, indent=2), flush=True)
