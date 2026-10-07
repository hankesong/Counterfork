import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import register as r

class RegistrationTests(unittest.TestCase):
    def test_v2_append_checks_predecessor_and_preserves_v1(self):
        manifest = {'caseId': {'hash': 'case'}, 'targetChainId': '1', 'fromBlock': '10', 'toBlock': '20', 'resultsHash': 'results'}
        with tempfile.TemporaryDirectory() as folder, patch.object(r, 'ROOT', Path(folder)), \
             patch.object(r, 'published_manifest', return_value=(manifest, 'digest', 'uri')), \
             patch.object(r, 'load', return_value={'resultsHash': 'results'}), \
             patch.object(r, 'run', return_value='case'), patch.object(r, 'sender', return_value='author'), \
             patch.object(r, 'chain', return_value=968), patch.object(r, 'call', side_effect=['1', 'original-v1', '2', 'original-v1']), \
             patch.object(r, 'send', return_value={'transactionHash': 'tx'}) as send, \
             patch.object(r, 'verify_record', return_value={}), patch.object(r, 'OFFICIAL', Path(folder) / 'official.json'):
            r.OFFICIAL.write_text('{"contract":"contract"}')
            r.submit({'BOT_PRIVATE_KEY': 'key'}, 2)
            self.assertEqual(send.call_args.args[1], 'submit-official-v2')
            self.assertFalse((Path(folder) / 'deployments/botchain-testnet-submit-parameters.json').exists())
            self.assertTrue((Path(folder) / 'deployments/botchain-testnet-submit-parameters-v2.json').exists())

    def test_mainnet_rejected_before_config(self):
        with patch.object(r, 'config') as config:
            with self.assertRaises(ValueError): r.network('mainnet')
            config.assert_not_called()

    def test_chain_677_refuses_send(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(r, 'JOURNAL', Path(folder)/'journal.json'), patch.object(r, 'run', return_value='677') as run:
            with self.assertRaises(RuntimeError): r.send({'BOT_TESTNET_RPC_URL':'test'}, 'test', ['contract'], 'key')
            self.assertEqual([c.args[:2] for c in run.call_args_list], [('cast','chain-id')])

    def test_chain_31337_also_refuses(self):
        with patch.object(r,'run',return_value='31337'):
            with self.assertRaises(RuntimeError): r.chain({'BOT_TESTNET_RPC_URL':'test'})

    def test_env_allowlist(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'.env').write_text('BOT_RPC_URL=forbidden\nBOT_CHAIN_ID=677\nBOT_PRIVATE_KEY=allowed\nBOT_TESTNET_CHAIN_ID=968\n')
            with patch.object(r,'ROOT',root), patch.dict(r.os.environ,{'BOT_RPC_URL':'forbidden-env'},clear=True):
                self.assertEqual(r.config(),{'BOT_PRIVATE_KEY':'allowed','BOT_TESTNET_CHAIN_ID':'968'})
                self.assertNotIn('BOT_RPC_URL',r.safe_env())
            r.SECRETS.clear()

    def test_production_source_has_no_mainnet_variable_access(self):
        for filename in ('register.py','reproduce.py'):
            source=(r.ROOT/'scripts'/filename).read_text(encoding='utf-8-sig')
            self.assertNotIn('BOT_RPC_URL',source)
            self.assertNotIn('BOT_CHAIN_ID',source)
            self.assertNotIn('phase5',source)

    def test_configured_bad_chain_rejected(self):
        with patch.object(r,'config',return_value={'BOT_TESTNET_CHAIN_ID':'677'}):
            with self.assertRaises(ValueError): r.network('testnet')

    def test_final_prebroadcast_call_is_chain_check(self):
        receipt={'status':'0x1','blockNumber':'0x2','logs':[]}
        with tempfile.TemporaryDirectory() as folder, patch.object(r,'JOURNAL',Path(folder)/'j.json'), patch.object(r,'run',side_effect=['968','0xabc',json.dumps(receipt)]) as run:
            r.send({'BOT_TESTNET_RPC_URL':'rpc','BOT_TESTNET_EXPLORER_URL':'https://scan'},'purpose',['contract'],'secret')
            self.assertEqual([c.args[:2] for c in run.call_args_list],[('cast','chain-id'),('cast','send'),('cast','receipt')])
            self.assertEqual(json.loads((Path(folder)/'j.json').read_text(encoding='utf-8'))['transactions'][0]['blockNumber'],2)

    def test_repeat_purpose_refused_without_network(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'j.json'
            path.write_text(json.dumps({'transactions':[{'purpose':'already'}]}))
            with patch.object(r,'JOURNAL',path),patch.object(r,'run') as run:
                with self.assertRaises(RuntimeError): r.send({},'already',[],'key')
                run.assert_not_called()

if __name__=='__main__': unittest.main()
