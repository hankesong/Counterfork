"""Offline evidence and experiment integrity checks; never access RPC."""
import copy
import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import phase3_batch as p


class Phase3Integrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = p.checked_load(p.DIR/'experiments.json')
        cls.rows = cls.doc['experiments']
        cls.accounts = p.checked_load(p.ROOT/'data/phase2/accounts.json')['accounts']
        cls.events = p.checked_load(p.ROOT/'data/phase2/events.json')['events']

    def test_first_event_and_top_twenty(self):
        self.assertEqual({r['borrower'] for r in self.rows},{a['borrower'] for a in self.accounts if a['top20']})
        for r in self.rows:
            es = [e for e in self.events if e['borrower']==r['borrower']]
            first = min(es,key=lambda e:(int(e['blockNumber']),int(e['logIndex'])))
            self.assertEqual(r['sample_event']['tx_hash'],first['tx_hash'])
            self.assertEqual(r['sample_event']['logIndex'],first['logIndex'])
            self.assertEqual(r['liquidation_count'],str(len(es)))
            if r['status']=='not_applicable':
                self.assertFalse(any(e['dai_related'] for e in es))
                self.assertEqual(r['groups'],{})
                self.assertEqual(r['reason'],'与 DAI 无关')

    def test_phase1_exact_regression(self):
        old=p.checked_load(p.ROOT/'data/phase1/single_account.json')
        row=next(r for r in self.rows if r['borrower']==old['borrower'])
        p.regression(row,old)
        altered=copy.deepcopy(row);altered['groups']['real']['shortfall']='0'
        with self.assertRaisesRegex(AssertionError,'regression mismatch'): p.regression(altered,old)

    def test_receipt_cutoff_and_price_source(self):
        for r in self.rows:
            if not r['groups']: continue
            e=r['sample_event'];proof=r['price_evidence']
            updates=proof['price_updates']
            for u in updates:
                log=u['log']
                self.assertLess((int(log['transactionIndex'],16),int(log['logIndex'],16)),(int(e['transactionIndex']),int(e['logIndex'])))
                self.assertEqual(u['price_raw'],str(int(u['event_price_raw'])*10**30//int(u['base_unit'])))
            dais=[u for u in updates if u['market']==p.CDAI.lower()]
            expected=dais[-1]['price_raw'] if dais else proof['reference_price_raw']
            self.assertEqual(expected,r['groups']['real']['dai_price_raw'])
            if dais:self.assertEqual(dais[-1]['source'],r['groups']['real']['price_source'])
            else:self.assertEqual(r['groups']['real']['price_source']['note'],'区块内无喂价')

    def test_critical_prices_validate_sign_flip(self):
        for r in self.rows:
            c=r['critical_price']
            if not c:continue
            self.assertTrue(c['derived'])
            if c['price_raw'] is None:
                self.assertTrue(c['reason']);continue
            self.assertTrue(c['sign_flip'])
            self.assertGreater(int(c['below']['liquidity']),0)
            self.assertGreater(int(c['above']['shortfall']),0)
            self.assertEqual(int(c['below']['dai_price_raw']),int(c['price_raw'])-10**14)
            self.assertEqual(int(c['above']['dai_price_raw']),int(c['price_raw'])+10**14)
            g=r['groups'];b0=int(g['1.00']['liquidity'])-int(g['1.00']['shortfall']);b1=int(g['1.30']['liquidity'])-int(g['1.30']['shortfall'])
            candidate=Decimal(10**18)-Decimal(b0)*Decimal(3*10**17)/Decimal(b1-b0)
            self.assertLess(abs(candidate-Decimal(c['price_raw'])),2)

    def test_acceptance_and_sensitivity(self):
        s=p.checked_load(p.DIR/'sensitivity.json')
        self.assertEqual(s,p.aggregate(self.rows,s['provenance']))
        for r in self.rows:
            if not r['groups']:continue
            g=r['groups']['real']
            self.assertEqual(r['status']=='passed',g['err']=='0' and int(g['shortfall'])>0)
        # A failed row must never enter formal statistics, even if a counterfactual has a shortfall.
        altered=copy.deepcopy(self.rows)
        row=next(r for r in altered if r['status']=='passed');row['status']='real_not_reproduced'
        reduced=p.aggregate(altered,s['provenance'])
        self.assertEqual(int(reduced['rows'][0]['included_accounts']),int(s['rows'][0]['included_accounts'])-1)

    def test_mock_rejected_at_any_depth(self):
        for obj in [{'provenance':{'mode':'UI_MOCK'}},{'rows':[{'provenance':{'mode':'UI_MOCK'}}]}]:
            with self.assertRaisesRegex(ValueError,'UI_MOCK'):p.reject_mock(obj)

    def test_all_output_numbers_are_strings_and_provenance(self):
        def check(x):
            if isinstance(x,dict):
                for v in x.values():check(v)
            elif isinstance(x,list):
                for v in x:check(v)
            else:self.assertFalse(isinstance(x,(int,float)) and not isinstance(x,bool))
        for path in p.DIR.rglob('*.json'):
            doc=p.checked_load(path);check(doc)
            p.require_evidence(doc,str(path))

    def test_phase2_status_union(self):
        from phase2_contract import analyzed_borrowers
        expected={r['borrower'] for r in self.rows if r['status']=='passed'}
        expected.add(p.checked_load(p.ROOT/'data/phase1/single_account.json')['borrower'])
        self.assertEqual(expected,analyzed_borrowers())
        self.assertEqual(expected,{a['borrower'] for a in self.accounts if a['status']=='analyzed'})


if __name__=='__main__': unittest.main()
