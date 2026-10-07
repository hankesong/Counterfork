import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import reproduce as r
from canonical import canonical_hash,load
from phase4_manifest import results_hash
import rpc_cache

class ReproductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=load(r.ROOT/'data/phase4/manifest.json')
        cls.digest=canonical_hash(cls.manifest)

    def test_bad_manifest_is_not_comparable(self):
        self.assertEqual(r.classify(self.manifest,'0x'+'0'*64,self.manifest['resultsHash']),'NOT_COMPARABLE')

    def test_bad_results_are_mismatch(self):
        self.assertEqual(r.classify(self.manifest,self.digest,'0x'+'1'*64),'MISMATCH')

    def test_match(self):
        self.assertEqual(r.classify(self.manifest,self.digest,self.manifest['resultsHash']),'MATCH')

    def test_context_precedes_results(self):
        self.assertEqual(r.classify(self.manifest,self.digest,'0x'+'1'*64,['different tool']),'CONTEXT_DIFFERENT')

    def test_context_different_never_attests(self):
        with patch.object(r.registry,'send') as send,patch.object(r.registry,'sender') as sender:
            self.assertIsNone(r.attest({}, {'status':'CONTEXT_DIFFERENT'},'key'))
            send.assert_not_called(); sender.assert_not_called()

    def test_not_comparable_never_attests(self):
        with patch.object(r.registry,'send') as send:
            self.assertIsNone(r.attest({}, {'status':'NOT_COMPARABLE'},'key'))
            send.assert_not_called()

    def test_mismatch_attests_observed_hash_false(self):
        report={'status':'MISMATCH','contract':'contract','caseId':'case','version':1,'observed_resultsHash':'0x'+'7'*64}
        with patch.object(r.registry,'sender',return_value='0xabc'),patch.object(r.registry,'call',side_effect=['false','0','true']),patch.object(r.registry,'send',return_value={'transactionHash':'tx'}) as send,patch.object(r.registry,'verify_record'):
            self.assertEqual(r.attest({},report,'key'),'tx')
            self.assertEqual(send.call_args.args[2][-2:],['false',report['observed_resultsHash']])

    def test_duplicate_attestation_refused(self):
        report={'status':'MATCH','contract':'contract','caseId':'case','version':1,'observed_resultsHash':'hash'}
        with patch.object(r.registry,'sender',return_value='0xabc'),patch.object(r.registry,'call',return_value='true'),patch.object(r.registry,'send') as send:
            with self.assertRaises(RuntimeError): r.attest({},report,'key')
            send.assert_not_called()

    def test_retry_transient_read(self):
        from unittest.mock import Mock
        action=Mock(side_effect=[RuntimeError('NETWORK_ERROR: handshake timed out'),'value'])
        with patch.object(r.time,'sleep'):
            self.assertEqual(r.retry_read(action,'test'),'value')
        self.assertEqual(action.call_count,2)

    def test_no_retry_calculation_failure(self):
        from unittest.mock import Mock
        action=Mock(side_effect=RuntimeError('incorrect sample block'))
        with self.assertRaises(RuntimeError): r.retry_read(action,'test')
        self.assertEqual(action.call_count,1)

    def test_read_retries_bounded(self):
        from unittest.mock import Mock
        action=Mock(side_effect=RuntimeError('NETWORK_ERROR'))
        with patch.object(r.time,'sleep'):
            with self.assertRaises(RuntimeError): r.retry_read(action,'test')
        self.assertEqual(action.call_count,6)

    def test_schema_rejected(self):
        m=copy.deepcopy(self.manifest);m['schemaVersion']='2'
        self.assertEqual(r.classify(m,canonical_hash(m),m['resultsHash']),'NOT_COMPARABLE')

    def test_definition_rejected(self):
        m=copy.deepcopy(self.manifest);m['resultsHashDefinition']['accountFields']=[]
        self.assertEqual(r.classify(m,canonical_hash(m),m['resultsHash']),'NOT_COMPARABLE')

    def test_results_projection_ignores_only_metadata(self):
        e=load(r.ROOT/'data/phase3/experiments.json');s=load(r.ROOT/'data/phase3/sensitivity.json')
        original=results_hash(e,s)
        e['implementation_sha256']='new';e['experiments'][0]['input_sha256']='new'
        self.assertEqual(results_hash(e,s),original)
        e['experiments'][0]['status']='different'
        self.assertNotEqual(results_hash(e,s),original)

    def test_cleanup_boundary(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): r.clean_directory(Path(folder).parent,folder)
            with self.assertRaises(ValueError): r.clean_directory(folder,folder)

    def test_rpc_cache_override_and_default(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'root';override=Path(folder)/'override'
            response=({}, {'jsonrpc':'2.0','id':1,'result':'0x1'})
            with patch.object(rpc_cache,'ROOT',root),patch.object(rpc_cache,'exchange',return_value=response) as exchange,patch.object(rpc_cache,'redact',side_effect=lambda s:s):
                with patch.dict(os.environ,{'RPC_CACHE_DIR':str(override)}):
                    self.assertEqual(rpc_cache.rpc('eth_chainId',[],url='unused'),'0x1')
                    self.assertEqual(rpc_cache.rpc('eth_chainId',[],url='unused'),'0x1')
                    self.assertEqual(exchange.call_count,1)
                with patch.dict(os.environ,{'RPC_CACHE_DIR':''}):
                    rpc_cache.rpc('eth_chainId',[],url='unused')
                self.assertEqual(len(list(override.glob('*.json'))),1)
                self.assertEqual(len(list((root/'data/rpc').glob('*.json'))),1)
                self.assertEqual(next(override.glob('*.json')).read_bytes(),next((root/'data/rpc').glob('*.json')).read_bytes())

    def test_segment_manifest_uses_override(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'RPC_CACHE_DIR':folder}),patch.object(rpc_cache,'rpc',return_value=[]):
            self.assertEqual(list(rpc_cache.iter_log_segments(1,2,{},max_span=2)),[(1,2,[])])
            self.assertEqual(len(list(Path(folder).glob('segments_*.json'))),1)

if __name__=='__main__': unittest.main()
