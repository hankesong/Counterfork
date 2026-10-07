import copy
import io
import json
from pathlib import Path
import ssl
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import manifest_v2 as m
import replay_rpc as rpc
import reproduce as r
import replay_session as session
from canonical import load, canonical_hash


class Response(io.BytesIO):
    def __init__(self, value, status=200):
        super().__init__(json.dumps(value).encode())
        self.code = status


class RetryTests(unittest.TestCase):
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': 'eth_call', 'params': []}

    def test_infura_precondition_is_retried_and_counted(self):
        bad = {'error': {'code': -32603, 'message': 'precondition failure'}}
        gateway = rpc.Gateway('https://secret.invalid/key')
        with patch.object(rpc, 'urlopen', side_effect=[Response(bad), Response({'result': 'ok'})]), patch.object(rpc.time, 'sleep') as sleep:
            self.assertEqual(gateway.exchange(self.payload)['result'], 'ok')
        self.assertEqual(gateway.stats, {'network_requests': 2, 'retries': 1, 'terminal_failures': 0})
        sleep.assert_called_once_with(2)

    def test_timeout_ssl_502_503_429_backoff_and_persistence(self):
        failures = [TimeoutError(), ssl.SSLError(), *[HTTPError('secret', c, 'x', {}, io.BytesIO(b'')) for c in (502, 503, 429)]]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'stats.json'
            gateway = rpc.Gateway('https://secret.invalid/key', path)
            with patch.object(rpc, 'urlopen', side_effect=failures + [Response({'result': 'ok'})]), patch.object(rpc.time, 'sleep') as sleep:
                self.assertEqual(gateway.exchange(self.payload)['result'], 'ok')
            self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4, 8, 16, 32])
            self.assertEqual(rpc.Gateway('different node', path).stats, {'network_requests': 6, 'retries': 5, 'terminal_failures': 0})
            self.assertNotIn('secret', path.read_text())

    def test_explicit_rpc_errors_are_not_retried(self):
        for code in (-32601, -32602, -32603, -32000):
            with self.subTest(code=code), patch.object(rpc, 'urlopen', return_value=Response({'error': {'code': code, 'message': 'invalid params'}})) as wire:
                self.assertEqual(rpc.Gateway('https://node.invalid').exchange(self.payload)['error']['code'], code)
                self.assertEqual(wire.call_count, 1)

    def test_retry_exhaustion_is_bounded_and_redacted(self):
        gateway = rpc.Gateway('https://secret.invalid/key')
        with patch.object(rpc, 'urlopen', side_effect=TimeoutError('secret')), patch.object(rpc.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'six attempts') as caught:
                gateway.exchange(self.payload)
        self.assertNotIn('secret', str(caught.exception))
        self.assertEqual(gateway.stats, {'network_requests': 6, 'retries': 5, 'terminal_failures': 1})

    def test_proxy_returns_json_without_credentials(self):
        gateway = rpc.Gateway('secret node')
        with patch.object(gateway, 'exchange', return_value={'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32602, 'message': 'secret key'}}):
            with gateway.serve() as local:
                with urlopen(Request(local, data=json.dumps(self.payload).encode()), timeout=3) as response:
                    value = json.loads(response.read())
        self.assertEqual(value['error']['code'], -32602)
        self.assertNotIn('secret', json.dumps(value))


class ProducerTests(unittest.TestCase):
    def test_v2_schema_and_rpc_independence(self):
        value = load(m.ROOT / 'data/phase4/manifest.json')
        value['schemaVersion'] = '2'
        value['producerCommits'] = {name: {'commit': m.P3_COMMIT, 'codeFingerprint': m.fingerprint(m.P3_COMMIT, m.P3)}
                                   for name in ('phase2', 'phase3', 'phase4')}
        value['context'] = {'tools': {'python': '3.14.6', 'forge': '1.8.5', 'cast': '1.8.5', 'solc': '0.8.30'},
                            'parameters': m.parameters(value)}
        for endpoint_hash in ('a' * 64, 'b' * 64):
            value['rpc_url_sha256'] = endpoint_hash
            self.assertEqual(r.classify(value, canonical_hash(value), value['resultsHash']), 'MATCH')
            self.assertEqual(r.classify(value, canonical_hash(value), '0x' + '0' * 64), 'MISMATCH')
        value['producerCommits']['phase2']['codeFingerprint']['filesInOrder'] = ['../escape']
        self.assertEqual(r.classify(value, canonical_hash(value), value['resultsHash']), 'NOT_COMPARABLE')

    def test_precise_historical_newline_cause(self):
        v1 = load(m.ROOT / 'data/phase4/manifest.json')
        self.assertEqual(m.historical_bytes(m.P3_COMMIT), v1['provenance']['phase3ImplementationSha256'])
        self.assertEqual(m.fingerprint(m.P3_COMMIT, m.P3)['sha256'], '3bb5fdb92ba118470826ed9d4ec4b623ccc979b0e6080e6c6239d06f1bd87f1b')
        self.assertNotEqual(m.fingerprint(m.P3_COMMIT, m.P3)['sha256'], v1['provenance']['phase3ImplementationSha256'])

    def test_archive_is_exact_and_caches_absent(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder) / 'phase3'
            r.checkout(m.P3_COMMIT, work)
            producer = {'codeFingerprint': m.fingerprint(m.P3_COMMIT, m.P3)}
            session.verify_producer(work, producer)
            for p in ('data/rpc', 'data/private', 'data/phase3', 'cache', 'out'):
                self.assertFalse((work / p).exists())
            (work / 'foundry.toml').write_text('changed')
            with self.assertRaises(ValueError):
                session.verify_producer(work, producer)

    def test_phase2_seed_weights_unchanged_after_annotations(self):
        old = json.loads(m.git('show', m.P2_COMMIT + ':data/phase2/accounts.json'))
        new = load(m.ROOT / 'data/phase2/accounts.json')
        for a, b in zip(old['accounts'], new['accounts']):
            self.assertEqual({k:v for k,v in a.items() if k != 'status'}, {k:v for k,v in b.items() if k != 'status'})


class ResumeTests(unittest.TestCase):
    def test_completed_account_survives_interruption_and_only_missing_runs(self):
        import types
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            work = base / 'work'
            work.mkdir()
            (base / 'inputs').mkdir()
            events = []
            accounts = []
            manifest = {'accounts': []}
            for i in range(2):
                borrower = '0x' + str(i+1) * 40
                e = {'tx_hash': str(i), 'logIndex': '0', 'blockNumber': '100', 'blockHash': 'block', 'transactionIndex': str(i),
                     'raw_log': dict.fromkeys(('address', 'topics', 'data', 'blockNumber', 'blockHash', 'transactionHash', 'transactionIndex', 'logIndex'), str(i))}
                events.append(e)
                accounts.append({'borrower': borrower, 'top20': True, 'rank': str(i+1), 'dai_related': False,
                                 'repay_usd_estimate_total': '1', 'events': [{'tx_hash': str(i), 'logIndex': '0'}]})
                manifest['accounts'].append({'borrower': borrower, 'sampleBlock': '100', 'forkBlock': '99'})
            r.registry.save(base / 'inputs/accounts.json', {'accounts': accounts})
            r.registry.save(base / 'inputs/events.json', {'events': events})
            r.registry.save(base / 'manifest.json', manifest)
            seen = []
            fail = [True]
            def call(method, params, **kwargs):
                if method == 'eth_chainId': return '0x1'
                seen.append(params[0])
                if params[0] == '1' and fail[0]: raise RuntimeError('Interrupted')
                return {'status': '0x1', 'logs': [events[int(params[0])]['raw_log']]}
            stats = {'network_requests': 0, 'cache_hits': 0}
            fake = {'rpc_cache': types.SimpleNamespace(rpc=call),
                    'rpc_transport': types.SimpleNamespace(STATS=stats, redact=str),
                    'phase2_events': types.SimpleNamespace(),
                    'phase3_batch': types.SimpleNamespace(write=r.registry.save, aggregate=lambda rows, proof: {'rows': []})}
            old_path = sys.path[:]
            try:
                with patch.dict(sys.modules, fake), patch.dict(r.os.environ, {'RPC_CACHE_DIR': str(work / 'data/rpc'), 'REPLAY_ETH_RPC_URL': 'http://127.0.0.1:1'}):
                    r.worker(work, base / 'manifest.json', base / 'result.json', 'quick')
                    self.assertFalse(load(base / 'result.json')['complete'])
                    self.assertEqual(len(list((base / 'checkpoints').glob('*.json'))), 1)
                    fail[0] = False
                    r.worker(work, base / 'manifest.json', base / 'result.json', 'quick')
                    self.assertTrue(load(base / 'result.json')['complete'])
                    self.assertEqual(seen, ['0', '1', '1'])
                    self.assertEqual(len(list((base / 'checkpoints').glob('*.json'))), 2)
            finally:
                sys.path[:] = old_path


if __name__ == '__main__':
    unittest.main()
