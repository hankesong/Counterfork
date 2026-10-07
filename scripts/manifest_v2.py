"""Append-only v2 manifest and reproducible Git-blob fingerprint audit."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

from canonical import canonical_hash, load, loads
from phase4_manifest import RESULTS_DEFINITION, results_hash

ROOT = Path(__file__).resolve().parents[1]
P3 = ['scripts/phase3_batch.py', 'test/Phase3.t.sol', 'test/Phase1.t.sol',
      'scripts/rpc_cache.py', 'scripts/rpc_transport.py', 'scripts/phase1_single.py',
      'scripts/phase0_check.py', 'scripts/phase2_contract.py', 'foundry.toml']
P2 = ['scripts/phase2_events.py', 'scripts/phase2_report.py', 'scripts/phase2_contract.py',
      'scripts/locate_phase0_sample.py', 'scripts/phase1_single.py', 'scripts/phase0_check.py',
      'scripts/rpc_cache.py', 'scripts/rpc_transport.py', 'foundry.toml']
# Exact surviving producer worktree byte layout; all other Phase 3 files were LF.
LF_LINES = list(range(10, 21)) + list(range(57, 71)) + [73, 83]
P2_COMMIT = '0faa08c447396a5c592b3f1842abd0ac2a181cb4'
P3_COMMIT = '655dba3665e6e213eea920c32f4aa185eb34a0c3'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)


def fingerprint(commit, paths):
    blobs = [git('show', commit + ':' + p) for p in paths]
    return {'algorithm': 'sha256-concatenated-git-blobs', 'filesInOrder': paths,
            'sha256': hashlib.sha256(b''.join(blobs)).hexdigest(),
            'fileSha256': {p: hashlib.sha256(b).hexdigest() for p, b in zip(paths, blobs)}}


def historical_bytes(commit):
    blobs = []
    for p in P3:
        b = git('show', commit + ':' + p)
        if p == 'scripts/phase2_contract.py':
            b = b''.join(line if i in LF_LINES else line.replace(b'\n', b'\r\n')
                         for i, line in enumerate(b.splitlines(keepends=True), 1))
        blobs.append(b)
    return hashlib.sha256(b''.join(blobs)).hexdigest()


def audit():
    v1 = load(ROOT / 'data/phase4/manifest.json')
    rows = []
    for commit in git('rev-list', '--reverse', v1['script_commit']).decode().split():
        exists = subprocess.run(['git', 'cat-file', '-e', commit + ':test/Phase3.t.sol'],
                                cwd=ROOT, capture_output=True).returncode == 0
        rows.append({'commit': commit, 'gitBlobSha256': fingerprint(commit, P3)['sha256'] if exists else None,
                     'historicalWorkingTreeSha256': historical_bytes(commit) if exists else None})
    return {'filesInOrder': P3, 'recordedSha256': v1['provenance']['phase3ImplementationSha256'],
            'commits': rows, 'historicalByteLayout': {'file': 'scripts/phase2_contract.py',
                'lfLines': LF_LINES, 'allOtherLines': 'CRLF', 'allOtherFiles': 'LF'},
            'diff': git('diff', P3_COMMIT, v1['script_commit'], '--', *P3).decode(),
            'conclusion': 'No raw Git-blob match. 655dba36 and ba031ad8 match with the surviving mixed newline layout. '
                          'Only foundry.toml changed in this interval, in 7c1d0889; rpc_transport.py did not change.'}


def validate_schema(m):
    if m.get('schemaVersion') not in ('1', '2') or m.get('hashAlgorithm') != 'keccak256-jcs' or m.get('resultsHashDefinition') != RESULTS_DEFINITION:
        raise ValueError('Unsupported manifest schema or results definition')
    if m['schemaVersion'] == '1':
        return
    if not re.fullmatch(r'[0-9a-f]{40}', m.get('script_commit', '')):
        raise ValueError('Invalid manifest generator commit')
    if set(m.get('producerCommits', {})) != {'phase2', 'phase3', 'phase4'}:
        raise ValueError('Missing producer commits')
    for producer in m['producerCommits'].values():
        if not re.fullmatch(r'[0-9a-f]{40}', producer.get('commit', '')):
            raise ValueError('Invalid producer commit')
        fp = producer['codeFingerprint']
        if fp['algorithm'] != 'sha256-concatenated-git-blobs' or not fp['filesInOrder'] or len(set(fp['filesInOrder'])) != len(fp['filesInOrder']):
            raise ValueError('Invalid fingerprint definition')
        if set(fp['filesInOrder']) != set(fp['fileSha256']):
            raise ValueError('Incomplete fingerprint')
        for p in fp['filesInOrder']:
            if '\\' in p or ':' in p or p.startswith('/') or '..' in p.split('/') or not p.startswith(('scripts/', 'test/', 'src/', 'foundry.toml')):
                raise ValueError('Unsafe source path')
        for digest in [fp['sha256'], *fp['fileSha256'].values()]:
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Invalid SHA-256')
    for name in ('python', 'forge', 'cast', 'solc'):
        if not isinstance(m['context']['tools'][name], str) or not m['context']['tools'][name]:
            raise ValueError('Missing tool version')
    if m['context']['parameters'] != parameters(m):
        raise ValueError('Experiment parameters inconsistent')
    if not re.fullmatch(r'0x[0-9a-f]{64}', m['resultsHash']):
        raise ValueError('Invalid results hash')


def parameters(m):
    return {'targetChainId': m['targetChainId'], 'fromBlock': m['fromBlock'], 'toBlock': m['toBlock'],
            'accounts': m['accounts'], 'experimentTemplates': m['experimentTemplates'],
            'prices': ['1.00', '1.05', '1.10', '1.20', '1.30'], 'evmVersion': 'istanbul',
            'sample': 'first liquidation per top20 borrower', 'state': 'N-1'}


def build():
    v1 = load(ROOT / 'data/phase4/manifest.json')
    m = copy.deepcopy(v1)
    script_commit = git('rev-parse', 'HEAD').decode().strip()
    # Generator itself must be committed; dirty unrelated files are not represented as source.
    for p in ('scripts/manifest_v2.py', 'scripts/reproduce.py', 'scripts/replay_rpc.py', 'scripts/replay_session.py'):
        if git('show', script_commit + ':' + p).replace(b'\r\n', b'\n') != (ROOT / p).read_bytes().replace(b'\r\n', b'\n'):
            raise ValueError('Commit generator and harness before generating v2')
    expected = results_hash(load(ROOT / 'data/phase3/experiments.json'), load(ROOT / 'data/phase3/sensitivity.json'))
    if expected != v1['resultsHash'] or historical_bytes(P3_COMMIT) != v1['provenance']['phase3ImplementationSha256']:
        raise ValueError('Historical result/fingerprint mismatch')
    for item in v1['files']:
        if canonical_hash(load(ROOT / item['path'])) != item['hash']:
            raise ValueError('Original evidence changed: ' + item['path'])
    p4paths = sorted(v1['scriptSha256'])
    m.update(schemaVersion='2', script_commit=script_commit,
             producerCommits={name: {'commit': commit, 'codeFingerprint': fingerprint(commit, paths)}
                for name, commit, paths in [('phase2', P2_COMMIT, P2), ('phase3', P3_COMMIT, P3),
                                           ('phase4', v1['script_commit'], p4paths)]})
    if m['producerCommits']['phase4']['codeFingerprint']['fileSha256'] != v1['scriptSha256']:
        raise ValueError('Phase 4 original script fingerprint mismatch')
    m['producerCommits']['phase3']['recordedWorkingTreeFingerprint'] = {
        'sha256': v1['provenance']['phase3ImplementationSha256'], 'byteLayout': audit()['historicalByteLayout'],
        'note': 'Historical byte layout only; replay executes unchanged Git blobs, without newline rewriting.'}
    m['scriptSha256'] = {p: hashlib.sha256(git('show', script_commit + ':' + p)).hexdigest()
                         for p in ('scripts/manifest_v2.py', 'scripts/reproduce.py', 'scripts/replay_rpc.py', 'scripts/replay_session.py')}
    m['context'] = {'tools': v1['provenance']['tools'] | {'solc': '0.8.30+commit.73712a01'}, 'parameters': parameters(m)}
    m['rpcPolicy'] = 'Endpoint is not context. Record URL SHA-256 only; each reproducer supplies its own Ethereum node.'
    m['reproductionNotes'] = 'Execute stage code at producerCommits. script_commit identifies the v2 generator. Quick reruns Phase 3 using hashed frozen Phase 2 seeds; full reruns Phase 2 then Phase 3. Phase 4 LLM prose is excluded from resultsHash.'
    m['reproduceCommand'] = 'python scripts/reproduce.py --network testnet --case compound-2020-11-26-dai --version 2 --level quick --eth-rpc-env ETH_RPC_URL_INFURA --attest'
    for key in ('experimentReplayCommand', 'freshRpcReplayCommand'):
        m.pop(key, None)
    m['quickInputs'] = [{'path': 'data/phase2/' + n, 'commit': P2_COMMIT,
                         'hash': canonical_hash(loads(git('show', P2_COMMIT + ':data/phase2/' + n).decode()))}
                        for n in ('accounts.json', 'events.json')]
    m['supersedesManifestHash'] = canonical_hash(v1)
    validate_schema(m)
    return m


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit', action='store_true')
    args = parser.parse_args()
    value = audit() if args.audit else build()
    path = ROOT / ('data/phase4/fingerprint-audit-v2.json' if args.audit else 'data/phase4/manifest-v2.json')
    encoded = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists() and path.read_text(encoding='utf-8') != encoded:
        raise ValueError('Append-only artifact already exists with different contents')
    path.write_text(encoded, encoding='utf-8', newline='\n')
    print(json.dumps({'path': path.relative_to(ROOT).as_posix(), 'hash': canonical_hash(value)}, indent=2))


if __name__ == '__main__':
    main()
