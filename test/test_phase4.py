"""Offline security, evidence, canonicalization and reproducibility contract tests."""
import copy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from canonical import canonical_bytes, canonical_hash, keccak256, loads
from phase4_common import (EXP, SENS, SUMMARY, HYP, Client, check_text, check_all_text,
    evidence, ref, resolve, sources, reject_mock, env_config)
from phase4_hypothesis import CANDIDATES, derived_evidence, validate_hypotheses
from phase4_audit import claim_specs, fixed_sections, validate_report, markdown
from phase4_manifest import (RESULTS_DEFINITION, cross_validate, results_hash,
                            require_clean, reproduction_status)


def fixture_hypotheses():
    return {'hypotheses': [{'id': key, 'reason': '事件摘要提示值得核查，不能据此认定原因。',
        'run_experiment': key == 'H1', 'template': 'dai_price_override' if key == 'H1' else None,
        'parameters': {'prices': [ref(SENS, f'/rows/{i}/price_usd') for i in range(5)]} if key == 'H1' else {},
        'status': 'EXPERIMENT_COVERED' if key == 'H1' else 'UNVERIFIED',
        'evidence_refs': [ref(SUMMARY, '/dai_related')]} for key in CANDIDATES]}


class ReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = sources()

    def test_bare_digits(self):
        for text in ('清算14个', '价格1.00', '0xf2df', 'H12', 'Phase 30', 'N−12', '账户１４个'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                check_text(text, self.data)

    def test_valid_reference_and_fixed_literals(self):
        check_text('N−1 Compound v2 2020-11-26 Phase 3 H1 H2 ' + ref(SENS, '/rows/0/liquidatable_accounts'), self.data)

    def test_invalid_reference(self):
        for token in (ref(SENS, '/rows/99'), ref(SENS, '/rows/-1'), ref(SENS, '/rows/00'),
                      ref(SENS, '/rows/0/~2bad'), ref('../.env', ''), ref(SUMMARY, '/missing'), '{{ref:bad}}'):
            with self.subTest(token=token), self.assertRaises(ValueError):
                check_text(token, self.data)

    def test_pointer_escaping(self):
        self.assertEqual(resolve(ref(SENS, '/a~1b/~0key'), {SENS: {'a/b': {'~key': 'ok'}}}), 'ok')

    def test_missing_evidence(self):
        for row in ({'claim': '结论'}, {'claim': '结论', 'evidence_refs': []}):
            with self.assertRaises(ValueError):
                evidence(row, self.data)

    def test_mock_anywhere(self):
        for obj in ({'provenance': {'mode': 'UI_MOCK'}}, {'nested': [{'mode': 'UI_MOCK'}]}, 'UI_MOCK'):
            with self.assertRaises(ValueError):
                reject_mock(obj)

    def test_json_numeric_output_rejected(self):
        with self.assertRaises(ValueError):
            check_all_text({'count': 2}, self.data)


class HypothesisAuditTests(unittest.TestCase):
    def setUp(self):
        self.data = sources()
        self.hyp = fixture_hypotheses()
        self.data[HYP] = {**copy.deepcopy(self.hyp), 'evidence_summary': derived_evidence(self.data)}
        self.report = {**fixed_sections(self.data), 'uncertainty': ['区块内操作与利息计提尚未隔离。'],
            'conclusions': [{**s, 'explanation': '只在固定状态和给定实验范围内解释。'} for s in claim_specs(self.data)]}

    def test_valid_contract(self):
        validate_hypotheses(self.hyp, self.data)
        validate_report(self.report, self.data)

    def test_disallowed_template(self):
        self.hyp['hypotheses'][0]['template'] = 'arbitrary_code'
        with self.assertRaises(ValueError):
            validate_hypotheses(self.hyp, self.data)

    def test_disallowed_price(self):
        self.data[SENS]['rows'][0]['price_usd'] = '2.00'
        with self.assertRaises(ValueError):
            validate_hypotheses(self.hyp, self.data)

    def test_actual_coverage_required(self):
        del self.data[EXP]['experiments'][0]['groups']['1.05']
        with self.assertRaises(ValueError):
            validate_hypotheses(self.hyp, self.data)

    def test_unverified_enforced(self):
        self.hyp['hypotheses'][1]['status'] = 'SUPPORTED'
        with self.assertRaises(ValueError):
            validate_hypotheses(self.hyp, self.data)

    def test_diagnostic_cannot_validate_hypothesis(self):
        row = next(r for r in self.report['conclusions'] if r['topic'] == 'other_asset_diagnostic')
        row['status'] = 'SUPPORTED'
        with self.assertRaises(ValueError):
            validate_report(self.report, self.data)

    def test_required_limitations(self):
        self.report['assumptions_and_limitations'].pop(0)
        with self.assertRaises(ValueError):
            validate_report(self.report, self.data)

    def test_required_coverage_and_evidence(self):
        self.report['conclusions'][0]['evidence_refs'] = []
        with self.assertRaises(ValueError):
            validate_report(self.report, self.data)

    def test_derived_counts_match_recorded_evidence(self):
        stats = self.data[HYP]['evidence_summary']
        self.assertEqual([stats[k]['count'] for k in ('passed', 'preexisting', 'not_reproduced', 'diagnostic_reproduced', 'unexplained')], ['14', '6', '5', '4', '1'])
        self.assertEqual(stats['critical']['count'], '19')

    def test_render_includes_all_limitations_and_values(self):
        report = {**self.report, 'model': 'offline-fixture'}
        rendered = markdown(report, self.data)
        for item in self.data[EXP]['limitations']:
            self.assertIn(item, rendered)
        self.assertIn('0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc', rendered)
        self.assertIn('补实验回路未实现', rendered)


class CanonicalTests(unittest.TestCase):
    def test_forbidden_types(self):
        for obj in (1.0, float('nan'), {1: 'bad'}, 2**53+1, -2**53-1):
            with self.assertRaises(ValueError):
                canonical_bytes(obj)
        self.assertEqual(canonical_bytes(2**53), b'9007199254740992')

    def test_forbidden_json(self):
        for text in ('{"a":1,"a":2}', '{"nested":{"a":1,"a":1}}', 'NaN', 'Infinity', '1.0', '1e2', '9007199254740993'):
            with self.assertRaises(ValueError):
                loads(text)

    def test_sort_and_utf8(self):
        self.assertEqual(canonical_bytes({'乙': '中文', 'a': '9007199254740993'}), '{"a":"9007199254740993","乙":"中文"}'.encode())

    def test_keccak_known_answers(self):
        self.assertEqual(keccak256(b''), '0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470')
        self.assertEqual(keccak256(b'abc'), '0x4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45')

    def test_cast_all_five_vectors(self):
        checks = cross_validate()
        self.assertEqual(len(checks), 5)
        self.assertTrue(all(c['match'] for c in checks))

    def test_results_hash_ignores_metadata(self):
        data = sources()
        before = results_hash(data[EXP], data[SENS])
        for obj in (data[EXP], data[SENS], data[EXP]['experiments'][0],
                    data[EXP]['experiments'][0]['groups']['real'], data[SENS]['rows'][0]):
            obj.update({'provenance': {'mode': 'LIVE'}, 'elapsed_seconds': '999', 'capturedAt': 'tomorrow', 'rpc_requests_this_run': '999'})
        self.assertEqual(results_hash(data[EXP], data[SENS]), before)
        data[EXP]['experiments'][0]['groups']['real']['shortfall'] = '1'
        self.assertNotEqual(results_hash(data[EXP], data[SENS]), before)

    def test_results_rejects_mock(self):
        data = sources()
        data[EXP]['provenance']['mode'] = 'UI_MOCK'
        with self.assertRaises(ValueError):
            results_hash(data[EXP], data[SENS])

    def test_reproduction_states(self):
        manifest = {'schemaVersion': '1', 'hashAlgorithm': 'keccak256-jcs', 'resultsHash': 'same', 'resultsHashDefinition': RESULTS_DEFINITION}
        digest = canonical_hash(manifest)
        for result, expected, actual, hashed, state, submit in (
            ('same', 'ctx', 'ctx', digest, 'MATCH', True), ('different', 'ctx', 'ctx', digest, 'MISMATCH', True),
            ('same', 'ctx', 'other', digest, 'CONTEXT_DIFFERENT', False), ('same', 'ctx', 'ctx', 'wrong', 'NOT_COMPARABLE', False)):
            got = reproduction_status(manifest, hashed, result, expected, actual)
            self.assertEqual((got['status'], got['submit']), (state, submit))

    def test_clean_precondition(self):
        with patch('phase4_manifest.git', return_value=' M elsewhere'):
            with self.assertRaises(ValueError):
                require_clean()


class CacheTests(unittest.TestCase):
    def test_cache_and_two_feedback_retries(self):
        data = sources()
        config = {'LLM_BASE_URL': 'https://offline.invalid/v1', 'LLM_MODEL': 'fixture-model', 'LLM_API_KEY': 'secret-test-key'}
        responses = ['{"claim":"裸数字12"}', '{"claim":"{{ref:data/phase3/sensitivity.json#/missing}}"}', '{"claim":"没有数字"}']
        def wire(req, timeout):
            self.assertEqual(req.full_url, 'https://offline.invalid/v1/chat/completions')
            self.assertEqual(json.loads(req.data)['response_format'], {'type': 'json_object'})
            return io.BytesIO(json.dumps({'choices': [{'message': {'content': responses.pop(0)}}]}).encode())
        with tempfile.TemporaryDirectory() as folder:
            with patch('urllib.request.urlopen', side_effect=wire):
                client = Client(config, Path(folder))
                value = client.ask('test prompt', {}, lambda v: check_all_text(v, data))
            self.assertEqual(client.requests, 3)
            self.assertEqual(len(client.rejections), 2)
            with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')):
                replay = Client(config, Path(folder), cache_only=True)
                self.assertEqual(replay.ask('test prompt', {}, lambda v: check_all_text(v, data)), value)
            self.assertEqual((replay.requests, replay.hits), (0, 3))
            self.assertEqual(replay.rejections, client.rejections)
            for path in Path(folder).glob('*.json'):
                self.assertNotIn(config['LLM_API_KEY'], path.read_text(encoding='utf-8'))

    def test_retry_exhaustion_stops(self):
        config = {'LLM_BASE_URL': 'https://offline.invalid/v1', 'LLM_MODEL': 'fixture', 'LLM_API_KEY': 'secret'}
        def wire(*args, **kwargs):
            return io.BytesIO(b'{"choices":[{"message":{"content":"not json"}}]}')
        with tempfile.TemporaryDirectory() as folder, patch('urllib.request.urlopen', side_effect=wire):
            client = Client(config, Path(folder))
            with self.assertRaisesRegex(ValueError, 'two retries'):
                client.ask('prompt', {}, lambda v: None)
            self.assertEqual(client.requests, 3)
            self.assertEqual(len(client.rejections), 3)

    def test_missing_env_stops(self):
        with tempfile.TemporaryDirectory() as folder, patch('phase4_common.ROOT', Path(folder)):
            with self.assertRaisesRegex(ValueError, 'LLM_BASE_URL, LLM_MODEL, LLM_API_KEY'):
                env_config()


if __name__ == '__main__':
    unittest.main()
