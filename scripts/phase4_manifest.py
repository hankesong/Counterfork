"""Offline manifest/hash contract shared with future reproduction clients."""
import hashlib
import platform
import subprocess
from canonical import canonical_bytes, canonical_hash, keccak256, load
from phase4_common import ROOT, EXP, SENS, SUMMARY, HYP, FEATURES, CONSTANTS, reject_mock, resolve

CASE_ID = 'compound-2020-11-26-dai'
RESULT_FIELDS = ('borrower', 'sample_event', 'groups', 'critical_price', 'status')
VOLATILE = ('provenance', 'capturedAt', 'generatedAt', 'timestamp', 'elapsed_seconds',
            'runtime', 'run_time', 'running_time', 'request_count', 'rpc_requests_this_run',
            'cache_hits', 'account_result_cache_hits', 'started_at', 'finished_at')
RESULTS_DEFINITION = {
    'algorithm': 'keccak256-jcs',
    'object': '{"experiments": account projections, "sensitivity": sensitivity.rows}',
    'accountFields': list(RESULT_FIELDS),
    'order': 'Preserve experiments and sensitivity.rows array order from source files.',
    'recursiveExcludedKeys': list(VOLATILE),
    'scope': 'Only deterministic Phase 3 results; excludes diagnostic, price_evidence, LLM outputs and all nonselected account/top-level fields.',
}
FILES = (SUMMARY, EXP, SENS, FEATURES, CONSTANTS, HYP, 'data/phase4/report.json')


def strip_volatile(value):
    if isinstance(value, dict):
        return {k: strip_volatile(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [strip_volatile(v) for v in value]
    return value


def results_object(experiments, sensitivity):
    reject_mock(experiments)
    reject_mock(sensitivity)
    return strip_volatile({'experiments': [{k: r[k] for k in RESULT_FIELDS} for r in experiments['experiments']],
                           'sensitivity': sensitivity['rows']})


def results_hash(experiments, sensitivity):
    return canonical_hash(results_object(experiments, sensitivity))


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, encoding='utf-8').rstrip('\r\n')


def require_clean():
    if git('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('worktree must be completely clean before Phase 4 run; commit own changes and wait for concurrent work')
    return git('rev-parse', 'HEAD')


def script_fingerprints():
    paths = sorted([ROOT / 'scripts/canonical.py', *ROOT.glob('scripts/phase4_*.py')])
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def versions():
    result = {'python': platform.python_version()}
    for name in ('cast', 'forge'):
        result[name] = subprocess.check_output([str(ROOT / '.tools/foundry' / (name + '.exe')), '--version'],
                                               encoding='utf-8').strip()
    return result


def cross_validate():
    vectors = [('empty', b''), ('abc', b'abc'),
        ('chinese_json', canonical_bytes({'说明': '中文调查', '账户': ['甲', '乙']})),
        ('large_experiments_json', canonical_bytes(load(ROOT / EXP))), ('caseId', CASE_ID.encode())]
    result = []
    for name, data in vectors:
        expected = subprocess.check_output([str(ROOT / '.tools/foundry/cast.exe'), 'keccak'],
            input=('0x' + data.hex()).encode('ascii')).decode('ascii').strip()
        actual = keccak256(data)
        if actual != expected:
            raise ValueError('cast cross-check failed: ' + name)
        result.append({'name': name, 'bytes': str(len(data)), 'keccak256': actual, 'cast': expected, 'match': True})
    return result


def build(script_commit, data, report):
    if git('rev-parse', 'HEAD') != script_commit:
        raise ValueError('HEAD changed during generation; manifest refused')
    # Other sessions may work concurrently; never pretend their dirty files are clean.
    for line in git('status', '--porcelain', '--untracked-files=all').splitlines():
        path = line[3:].strip('"')
        if not (path.startswith('data/phase4/') or path == 'docs/phase4.md'):
            raise ValueError('unrelated workspace changes during generation; manifest refused')
    accounts = []
    for row in data[EXP]['experiments']:
        accounts.append({'borrower': row['borrower'], 'sampleBlock': row['sample_event']['blockNumber'],
            'forkBlock': str(int(row['sample_event']['blockNumber']) - 1), 'status': row['status'],
            'priceSources': {k: v['price_source'] for k, v in row['groups'].items()}})
    return {'schemaVersion': '1', 'hashAlgorithm': 'keccak256-jcs',
        'caseId': {'text': CASE_ID, 'hash': keccak256(CASE_ID.encode())}, 'targetChainId': '1',
        'fromBlock': data[SUMMARY]['window']['first']['block'], 'toBlock': data[SUMMARY]['window']['last']['block'],
        'repository': 'https://github.com/hankesong/Counterfork', 'script_commit': script_commit,
        'scriptSha256': script_fingerprints(),
        'experimentTemplates': [{'hypothesis': r['id'], 'template': r['template'],
            'parameters': {'prices': [resolve(t, data)
                                     for t in r['parameters']['prices']]}}
            for r in data[HYP]['hypotheses'] if r['run_experiment']],
        'accounts': accounts,
        'reproduceCommand': 'python scripts/phase4_run.py --cache-only',
        'experimentReplayCommand': 'python scripts/phase3_batch.py --cache-only --rerun-fork',
        'freshRpcReplayCommand': 'python scripts/phase3_batch.py --rerun-fork',
        'reproductionNotes': 'Fetch this artifact commit, verify the manifest hash, checkout script_commit in an isolated worktree; preserve frozen LLM cache separately. Phase 5g must use an isolated clean RPC/Foundry cache for independent replay; then compare resultsHash using resultsHashDefinition. Phase 4 does not rerun or modify Phase 2/3.',
        'files': [{'path': p, 'hash': canonical_hash(report if p.endswith('/report.json') else data[p])} for p in FILES],
        'resultsHashDefinition': RESULTS_DEFINITION, 'resultsHash': results_hash(data[EXP], data[SENS]),
        'reportHash': canonical_hash(report),
        'provenance': {'mode': 'FROZEN', 'source': 'Frozen Ethereum mainnet evidence; no chain submission',
            'experimentProvenance': data[EXP]['provenance'], 'summaryProvenance': data[SUMMARY]['provenance'],
            'rpcContext': 'Ethereum mainnet archive responses cached by Phase 2/3; endpoint credentials intentionally omitted',
            'phase3ImplementationSha256': data[EXP]['implementation_sha256'], 'tools': versions(),
            'model': report['model']}}


def verify_manifest(manifest, expected_hash):
    if manifest.get('schemaVersion') != '1' or manifest.get('hashAlgorithm') != 'keccak256-jcs':
        raise ValueError('NOT_COMPARABLE: unsupported schema')
    if canonical_hash(manifest) != expected_hash:
        raise ValueError('NOT_COMPARABLE: manifest hash mismatch')
    if manifest.get('resultsHashDefinition') != RESULTS_DEFINITION:
        raise ValueError('NOT_COMPARABLE: results definition mismatch')
    if [f['path'] for f in manifest['files']] != list(FILES):
        raise ValueError('NOT_COMPARABLE: invalid file list')
    for item in manifest['files']:
        value = load(ROOT / item['path'])
        reject_mock(value)
        if canonical_hash(value) != item['hash']:
            raise ValueError('NOT_COMPARABLE: source file hash mismatch: ' + item['path'])
    if canonical_hash(load(ROOT / 'data/phase4/report.json')) != manifest['reportHash']:
        raise ValueError('NOT_COMPARABLE: report hash mismatch')


def reproduction_status(manifest, expected_hash, observed_results_hash, expected_context, actual_context):
    """Pure classification, no network or transaction. Caller verifies source files separately."""
    if (manifest.get('schemaVersion') != '1' or manifest.get('hashAlgorithm') != 'keccak256-jcs'
            or manifest.get('resultsHashDefinition') != RESULTS_DEFINITION
            or canonical_hash(manifest) != expected_hash):
        return {'status': 'NOT_COMPARABLE', 'matched': None, 'submit': False}
    if expected_context != actual_context:
        return {'status': 'CONTEXT_DIFFERENT', 'matched': None, 'submit': False}
    matched = manifest['resultsHash'] == observed_results_hash
    return {'status': 'MATCH' if matched else 'MISMATCH', 'matched': matched, 'submit': True}
