"""Offline integrity checks using the real Phase 1 receipt and cached header."""
import copy
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import phase2_events as p


class EventIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.setup = p.load(p.DIR / 'setup.json')
        cls.sample = p.load(p.ROOT / 'data/phase1/sample.json')
        n = cls.sample['liquidation_block']
        cls.headers = {n: p.load(p.cache_path('eth_getBlockByNumber', [hex(n), False]))['result']}

    def log(self):
        return copy.deepcopy(self.sample['log'])

    def test_real_sample_decodes_exactly(self):
        e = p.decode([self.log()], self.setup, self.headers)[0]
        for key in ('liquidator', 'borrower', 'repayAmount', 'cTokenCollateral', 'seizeTokens'):
            self.assertEqual(e[key], self.sample[key])
        self.assertEqual(e['logIndex'], '59')
        self.assertTrue(e['dai_related'])

    def test_rejects_wrong_block_hash(self):
        log = self.log()
        log['blockHash'] = '0x' + '00' * 32
        with self.assertRaises(AssertionError):
            p.decode([log], self.setup, self.headers)

    def test_rejects_unknown_emitter(self):
        log = self.log()
        log['address'] = '0x' + '00' * 20
        with self.assertRaises(AssertionError):
            p.decode([log], self.setup, self.headers)

    def test_rejects_wrong_topic(self):
        log = self.log()
        log['topics'] = ['0x' + '00' * 32]
        with self.assertRaises(AssertionError):
            p.decode([log], self.setup, self.headers)

    def test_rejects_wrong_transaction_position(self):
        log = self.log()
        log['transactionIndex'] = '0x0'
        with self.assertRaises(AssertionError):
            p.decode([log], self.setup, self.headers)

    def test_rejects_duplicates(self):
        with self.assertRaises(AssertionError):
            p.decode([self.log(), self.log()], self.setup, self.headers)

    def test_decimal_scaling_across_underlying_precisions(self):
        # Two tokens repaid at $3.50: 6-, 8-, and 18-decimal assets all equal $7.
        for decimals in (6, 8, 18):
            raw_amount = 2 * 10**decimals
            raw_price = 35 * 10**(35 - decimals)
            self.assertEqual(p.decimal_scaled(raw_amount * raw_price, 36), '7')

    def test_tiny_usd_amount_not_rounded_to_zero(self):
        self.assertEqual(p.decimal_scaled(1, 36), '0.' + '0' * 35 + '1')

    def test_complete_outputs_reconcile(self):
        events = p.load(p.DIR / 'events.json')['events']
        accounts = p.load(p.DIR / 'accounts.json')['accounts']
        summary = p.load(p.DIR / 'summary.json')
        key = lambda e: (int(e['blockNumber']), int(e['logIndex']))
        self.assertEqual(events, sorted(events, key=key))
        refs = {(e['tx_hash'], e['logIndex']) for e in events}
        self.assertEqual(len(refs), len(events))
        total = sum(p.Decimal(e['repay_usd_estimate']) for e in events)
        self.assertEqual(total, p.Decimal(summary['total']['repay_usd_estimate']))
        self.assertEqual(total, sum(p.Decimal(a['repay_usd_estimate_total']) for a in accounts))
        self.assertEqual(total, sum(p.Decimal(m['repay_usd_estimate']) for m in summary['market_totals']))
        self.assertEqual(len(events), sum(int(a['liquidation_count']) for a in accounts))
        self.assertEqual(len(events), sum(int(m['event_count']) for m in summary['market_totals']))
        self.assertEqual(len(accounts), int(summary['total']['borrower_count']))
        for a in accounts:
            rows = [e for e in events if e['borrower'] == a['borrower']]
            self.assertEqual(p.Decimal(a['repay_usd_estimate_total']), sum(p.Decimal(e['repay_usd_estimate']) for e in rows))
            self.assertEqual(a['events'], [{'tx_hash': e['tx_hash'], 'logIndex': e['logIndex']} for e in rows])
        self.assertEqual([a['top20'] for a in accounts], [i < 20 for i in range(len(accounts))])

    def test_complete_output_numbers_are_strings(self):
        def check(obj):
            if isinstance(obj, dict):
                for value in obj.values():
                    check(value)
            elif isinstance(obj, list):
                for value in obj:
                    check(value)
            else:
                self.assertFalse(isinstance(obj, (int, float)) and not isinstance(obj, bool))
        for name in ('events', 'accounts', 'summary'):
            check(p.load(p.DIR / (name + '.json')))

    def test_display_exact_without_decimal_rounding(self):
        event = {'borrower': '0x12345678901234567890123456789012345678abcd',
                 'repaid_market_symbol': 'cTEST', 'blockNumber': '42',
                 'underlying_decimals': '18', 'repayAmount': str(10**120 + 123)}
        view = p.display(event)
        self.assertEqual(view['borrower_short'], '0x1234…abcd')
        self.assertEqual(view['repay_amount'], '1' + '0' * 102 + '.000000000000000123')
        event.update(underlying_decimals='0', repayAmount='7')
        self.assertEqual(p.display(event)['repay_amount'], '7')
        for row in p.load(p.DIR / 'events.json')['events']:
            view = row['display']
            self.assertEqual(view['block'], row['blockNumber'])
            self.assertEqual(view['market_symbol'], row['repaid_market_symbol'])
            self.assertEqual(int(view['repay_amount'].replace('.', '')), int(row['repayAmount']))

    def test_status_requires_accepted_file(self):
        from phase2_contract import analyzed_borrowers
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'result.json'
            self.assertEqual(analyzed_borrowers(path), set())
            result = p.load(p.ROOT / 'data/phase1/single_account.json')
            p.save(path, result)
            self.assertEqual(analyzed_borrowers(path), {result['borrower']})
            result['status'] = 'failed'
            p.save(path, result)
            self.assertEqual(analyzed_borrowers(path), set())
            result['status'] = 'passed'
            result['groups']['real']['shortfall'] = '0'
            p.save(path, result)
            self.assertEqual(analyzed_borrowers(path), set())
        accounts = p.load(p.DIR / 'accounts.json')['accounts']
        actual = {a['borrower'] for a in accounts if a['status'] == 'analyzed'}
        self.assertEqual(actual, analyzed_borrowers())
        self.assertEqual(len(actual), 1)
        self.assertTrue(all(a['status'] in {'pending', 'analyzed'} for a in accounts))

    def test_report_rejects_mock_in_any_input(self):
        import phase2_report as report
        documents = {name: p.load(p.DIR / (name + '.json')) for name in ('summary', 'accounts', 'events')}
        for rejected in documents:
            altered = copy.deepcopy(documents)
            altered[rejected]['provenance']['mode'] = 'UI_MOCK'
            with patch.object(report, 'load', side_effect=lambda path: altered[path.stem]):
                with self.assertRaisesRegex(ValueError, 'UI_MOCK'):
                    report.main()

    def test_provenance_is_stable_and_invalid_modes_rejected(self):
        from phase2_contract import provenance, require_evidence
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            p.save(folder / 'runs.json', [{'started_utc': '2026-10-07T03:28:30+00:00',
                                         'stages': [{'stage': 'logs', 'rpc_requests': '1'}]}])
            first = provenance(folder, 1)
            second = provenance(folder, 0)
            self.assertEqual(first['mode'], 'LIVE')
            self.assertEqual(second['mode'], 'FROZEN')
            self.assertEqual(first['capturedAt'], second['capturedAt'])
            self.assertEqual(first['capturedAt'], '2026-10-07T03:28:30Z')
            second['mode'] = 'UNKNOWN'
            with self.assertRaisesRegex(ValueError, 'invalid'):
                require_evidence({'provenance': second}, 'test')

    def test_original_fields_unchanged(self):
        original_path = p.ROOT / 'data/private/phase2_before_contract.json'
        if not original_path.exists():
            self.skipTest('Local pre-migration snapshot is not distributed')
        old = p.load(original_path)
        current_events = p.load(p.DIR / 'events.json')['events']
        current_accounts = p.load(p.DIR / 'accounts.json')['accounts']
        self.assertEqual([{k: v for k, v in e.items() if k != 'display'} for e in current_events], old['events'])
        self.assertEqual([{k: v for k, v in a.items() if k != 'status'} for a in current_accounts], old['accounts'])
        self.assertEqual({k: v for k, v in p.load(p.DIR / 'summary.json').items() if k != 'provenance'}, old['summary'])


if __name__ == '__main__':
    unittest.main()
