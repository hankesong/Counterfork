"""Chain-968-only official registration. No mainnet configuration or sending."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.request import urlopen
from canonical import canonical_hash, load, loads

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT / 'deployments/botchain-testnet-official.json'
JOURNAL = ROOT / 'deployments/botchain-testnet-registrations.json'
CASE = 'compound-2020-11-26-dai'
NOTICE = '测试网正式演示，不计入比赛有效部署（比赛只认主网）'
ALLOWED = ('BOT_TESTNET_RPC_URL', 'BOT_TESTNET_CHAIN_ID', 'BOT_TESTNET_EXPLORER_URL', 'BOT_PRIVATE_KEY')
SECRETS = []


def config(names=ALLOWED):
    values = {}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            name, sep, value = line.partition('=')
            if sep and name.strip() in names:
                values[name.strip()] = value.strip().strip('\"\'')
    for name in names:
        if name in os.environ:
            values[name] = os.environ[name]
    SECRETS.extend(v for k, v in values.items() if v and ('KEY' in k or 'RPC' in k))
    return values


def safe_env():
    names = ('SystemRoot', 'WINDIR', 'PATH', 'PATHEXT', 'TEMP', 'TMP', 'COMSPEC', 'USERPROFILE', 'HOME')
    return {k: os.environ[k] for k in names if k in os.environ} | {'NO_COLOR': '1', 'PYTHONIOENCODING': 'utf-8'}


def redact(value):
    text = str(value)
    for secret in sorted(set(SECRETS), key=len, reverse=True):
        text = text.replace(secret, '[redacted]')
    return re.sub(r'https?://[^\s\"<>]+', '[URL]', text)


def run(tool, *args, cwd=None, env=None, timeout=180):
    exe = ROOT / '.tools/foundry' / (tool + '.exe') if tool in ('cast', 'forge') else tool
    # Empty working directory prevents Foundry from loading the repository .env.
    with tempfile.TemporaryDirectory(prefix='registry-command-') as clean:
        proc = subprocess.run([str(exe), *map(str, args)], cwd=cwd or clean,
                              env=env or safe_env(), capture_output=True, text=True,
                              encoding='utf-8', errors='replace', timeout=timeout)
    if proc.returncode:
        raise RuntimeError(redact(proc.stdout + proc.stderr))
    return proc.stdout.strip()


def save(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if any(s in text for s in SECRETS if s):
        raise RuntimeError('Secret in output refused')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(text, encoding='utf-8')
    temp.replace(path)


def network(name):
    if name != 'testnet':
        raise ValueError('mainnet sending is not implemented; only testnet 968 is allowed')
    values = config()
    if values.get('BOT_TESTNET_CHAIN_ID', '968') != '968':
        raise ValueError('Configured chain ID must be 968')
    return values | {'BOT_TESTNET_RPC_URL': values.get('BOT_TESTNET_RPC_URL') or 'https://rpc.bohr.life',
                     'BOT_TESTNET_EXPLORER_URL': values.get('BOT_TESTNET_EXPLORER_URL') or 'https://scan.bohr.life'}


def chain(values):
    actual = int(run('cast', 'chain-id', '--rpc-url', values['BOT_TESTNET_RPC_URL']))
    if actual != 968:
        raise RuntimeError(f'Chain ID {actual} is not 968; transaction refused')
    return actual


def call(values, contract, signature, *args, decoded=False):
    extra = ['--json'] if decoded else []
    result = run('cast', 'call', contract, signature, *args, '--rpc-url', values['BOT_TESTNET_RPC_URL'], *extra)
    return json.loads(result) if decoded else result


def number(value):
    return int(value, 16) if isinstance(value, str) and value.startswith('0x') else int(value)


def sender(key):
    if not key:
        raise ValueError('Missing signing key')
    return run('cast', 'wallet', 'address', '--private-key', key)


def send(values, purpose, args, key):
    journal = json.loads(JOURNAL.read_text(encoding='utf-8')) if JOURNAL.exists() else {'notice': NOTICE, 'chain_id': 968, 'transactions': []}
    if any(t['purpose'] == purpose for t in journal['transactions']):
        raise RuntimeError('Purpose already journaled; inspect receipt before retrying: ' + purpose)
    chain(values)  # Must be the final external operation before EVERY broadcast.
    tx = run('cast', 'send', '--rpc-url', values['BOT_TESTNET_RPC_URL'], '--chain', '968',
             '--private-key', key, '--legacy', '--gas-price', '20000000000', '--async', *args)
    entry = {'purpose': purpose, 'transactionHash': tx, 'explorer': values['BOT_TESTNET_EXPLORER_URL'].rstrip('/') + '/tx/' + tx}
    journal['transactions'].append(entry)
    save(JOURNAL, journal)
    receipt = json.loads(run('cast', 'receipt', tx, '--rpc-url', values['BOT_TESTNET_RPC_URL'], '--json'))
    entry.update(blockNumber=number(receipt['blockNumber']), receipt=receipt)
    save(JOURNAL, journal)
    if number(receipt['status']) != 1:
        raise RuntimeError('Transaction reverted: ' + tx)
    return entry


def verified(entry, readback):
    journal = json.loads(JOURNAL.read_text(encoding='utf-8'))
    for tx in journal['transactions']:
        if tx['transactionHash'] == entry['transactionHash']:
            tx['readback'] = readback
    save(JOURNAL, journal)


def verify_record(values, contract, entry, getter, args, encoding, fields, event, case_id, event_encoding, event_fields):
    receipt = entry['receipt']
    block = json.loads(run('cast', 'rpc', 'eth_getBlockByNumber', receipt['blockNumber'], 'false', '--rpc-url', values['BOT_TESTNET_RPC_URL']))
    fields = fields + [number(block['timestamp']), number(receipt['blockNumber'])]
    expected = run('cast', 'abi-encode', encoding, '(' + ','.join(map(str, fields)) + ')')
    actual = call(values, contract, getter, *args)
    if expected.lower() != actual.lower():
        raise RuntimeError('Record fields differ')
    logs = receipt['logs']
    topic = run('cast', 'keccak', event)
    data = run('cast', 'abi-encode', event_encoding, *event_fields)
    if len(logs) != 1 or logs[0]['address'].lower() != contract.lower() or [s.lower() for s in logs[0]['topics']] != [topic.lower(), case_id.lower()] or logs[0]['data'].lower() != data.lower():
        raise RuntimeError('Registry event mismatch')
    result = {'all_fields_verified': True, 'fields': fields, 'event_verified': event, 'actual_abi': actual}
    verified(entry, result)
    return result


def published_manifest(version=1):
    if version not in (1, 2):
        raise ValueError('Only manifest versions 1 and 2 are supported')
    path = 'data/phase4/manifest-v2.json' if version == 2 else 'data/phase4/manifest.json'
    manifest = load(ROOT / path)
    from manifest_v2 import validate_schema
    validate_schema(manifest)
    if manifest['schemaVersion'] != str(version):
        raise ValueError('Manifest version mismatch')
    digest = canonical_hash(manifest)
    label = 'v2 manifestHash' if version == 2 else 'manifestHash'
    recorded = re.search(label + r'：`(0x[0-9a-f]{64})`', (ROOT / 'docs/phase4.md').read_text(encoding='utf-8')).group(1)
    if digest != recorded:
        raise ValueError('Manifest hash differs from docs/phase4.md')
    commit = run('git', 'log', '-1', '--format=%H', '--', path, cwd=ROOT)
    remote = run('git', 'ls-remote', 'origin', cwd=ROOT)
    branches = run('git', 'branch', '-r', '--contains', commit, cwd=ROOT).splitlines()
    verified_remote = False
    for branch in branches:
        branch = branch.strip()
        if branch.startswith('origin/') and ' -> ' not in branch:
            head = run('git', 'rev-parse', branch, cwd=ROOT)
            if head + '\trefs/heads/' + branch[len('origin/'):] in remote.splitlines():
                verified_remote = True
    if not verified_remote:
        raise RuntimeError('Please push the manifest commit to origin before registration')
    frozen = loads(run('git', 'show', commit + ':' + path, cwd=ROOT))
    uri = f'https://raw.githubusercontent.com/hankesong/Counterfork/{commit}/{path}'
    from replay_rpc import read_retry
    def download():
        with urlopen(uri, timeout=45) as response:
            return loads(response.read().decode('utf-8'))
    downloaded = read_retry(download)
    if canonical_hash(frozen) != digest or canonical_hash(downloaded) != digest:
        raise RuntimeError('Published manifest differs; please push the correct artifact before registration')
    return manifest, digest, uri


def deploy(values):
    if OFFICIAL.exists():
        raise RuntimeError('Official deployment already recorded; refusing repeat deployment')
    key = values.get('BOT_PRIVATE_KEY')
    author = sender(key)
    old = json.loads((ROOT / 'deployments/botchain-testnet.json').read_text(encoding='utf-8'))
    if author.lower() != old['deployer'].lower():
        raise ValueError('Signer differs from rehearsal deployer')
    with tempfile.TemporaryDirectory(prefix='registry-build-') as folder:
        temp = Path(folder)
        (temp / 'src').mkdir()
        shutil.copy2(ROOT / 'src/InvestigationRegistry.sol', temp / 'src/InvestigationRegistry.sol')
        solc = (ROOT / '.tools/solc.exe').as_posix()
        (temp / 'foundry.toml').write_text(f'[profile.default]\nsolc = "{solc}"\nevm_version = "paris"\noptimizer = true\noptimizer_runs = 200\n', encoding='utf-8')
        run('forge', 'build', '--offline', cwd=temp)
        artifact = json.loads((temp / 'out/InvestigationRegistry.sol/InvestigationRegistry.json').read_text())
    entry = send(values, 'deploy-official', ['--create', artifact['bytecode']['object']], key)
    contract = entry['receipt']['contractAddress']
    code = run('cast', 'code', contract, '--rpc-url', values['BOT_TESTNET_RPC_URL'])
    expected = artifact['deployedBytecode']['object']
    if code.lower().removeprefix('0x') != expected.lower().removeprefix('0x'):
        raise RuntimeError('Deployed bytecode differs')
    record = {'notice': NOTICE, 'chain_id': 968, 'contract': contract, 'deployer': author,
              'deployment': entry, 'compiler': {'forge_version': run('forge', '--version'), 'solc_version': '0.8.30+commit.73712a01', 'evm_version': 'paris', 'optimizer': True, 'optimizer_runs': 200},
              'source_sha256': hashlib.sha256((ROOT / 'src/InvestigationRegistry.sol').read_bytes()).hexdigest(), 'bytecode_verified': True}
    save(OFFICIAL, record)
    verified(entry, {'runtime_bytecode_verified': True, 'contract': contract})
    print(json.dumps(record, ensure_ascii=False, indent=2))


def submit(values, version=1):
    manifest, digest, uri = published_manifest(version)
    contract = json.loads(OFFICIAL.read_text(encoding='utf-8'))['contract']
    case_id = run('cast', 'keccak', CASE)
    if case_id != manifest['caseId']['hash'] or manifest['targetChainId'] != '1':
        raise ValueError('Case or target mismatch')
    if call(values, contract, 'latestVersion(bytes32)(uint256)', case_id) != str(version - 1):
        raise RuntimeError('Append requires exactly the preceding version; refusing duplicate or skipped version')
    prior = None
    if version == 2:
        prior = call(values, contract, 'getInvestigation(bytes32,uint256)', case_id, 1)
        if manifest['resultsHash'] != load(ROOT / 'data/phase4/manifest.json')['resultsHash']:
            raise ValueError('v2 must preserve v1 resultsHash')
    author = sender(values.get('BOT_PRIVATE_KEY'))
    parameters = dict(caseId=case_id, targetChainId=1, fromBlock=int(manifest['fromBlock']), toBlock=int(manifest['toBlock']), manifestHash=digest, manifestURI=uri, contract=contract, chain_id=chain(values))
    suffix = '-v2' if version == 2 else ''
    save(ROOT / f'deployments/botchain-testnet-submit-parameters{suffix}.json', parameters)
    print(json.dumps(parameters, ensure_ascii=False, indent=2), flush=True)
    fields = [1, parameters['fromBlock'], parameters['toBlock'], digest, uri]
    entry = send(values, f'submit-official-v{version}', [contract, 'submitInvestigation(bytes32,uint256,uint256,uint256,bytes32,string)', case_id, *fields], values['BOT_PRIVATE_KEY'])
    result = verify_record(values, contract, entry, 'getInvestigation(bytes32,uint256)', [case_id, version],
                          'f((address,uint256,uint256,uint256,bytes32,string,uint256,uint256))', [author, *fields],
                          'InvestigationSubmitted(bytes32,uint256,address,bytes32)', case_id, 'f(uint256,address,bytes32)', [version, author, digest])
    if call(values, contract, 'latestVersion(bytes32)(uint256)', case_id) != str(version):
        raise RuntimeError('Latest version mismatch')
    if prior is not None and call(values, contract, 'getInvestigation(bytes32,uint256)', case_id, 1) != prior:
        raise RuntimeError('Version 1 readback changed')
    print(json.dumps({'transactionHash': entry['transactionHash'], 'readback': result}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'deploy', 'submit'])
    parser.add_argument('--network', default='testnet', choices=['testnet', 'mainnet'])
    parser.add_argument('--version', type=int, choices=[1, 2], default=1)
    args = parser.parse_args()
    values = network(args.network)
    if args.command == 'check':
        _, digest, uri = published_manifest(args.version)
        print(json.dumps({'manifestHash': digest, 'manifestURI': uri, 'chain_id': chain(values)}))
    elif args.command == 'deploy':
        deploy(values)
    else:
        submit(values, args.version)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('ERROR:', redact(exc))
        raise SystemExit(1) from None
