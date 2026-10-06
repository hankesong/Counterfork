"""Offline regression tests: splitting, replay, read-only guard, global timing."""
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import rpc_cache
import rpc_transport


class CacheTests(unittest.TestCase):
    def test_halving_and_complete_cache_replay(self):
        attempts = []

        def exchange(_url, payload):
            p = payload["params"][0]
            start, end = int(p["fromBlock"], 16), int(p["toBlock"], 16)
            attempts.append((start, end))
            if end - start + 1 > 2:
                return {}, {"error": {"code": 35, "message": "range too large"}}
            return {}, {"jsonrpc": "2.0", "id": 1, "result": []}

        with tempfile.TemporaryDirectory() as tmp, patch.object(rpc_cache, "ROOT", Path(tmp)), patch.object(rpc_cache, "exchange", exchange), patch.object(rpc_cache, "redact", str):
            first = list(rpc_cache.iter_log_segments(10, 17, {}, max_span=8, url="offline"))
            self.assertEqual([(a, b) for a, b, _ in first], [(10, 11), (12, 13), (14, 15), (16, 17)])
            self.assertEqual(attempts[:3], [(10, 17), (10, 13), (10, 11)])
            attempts.clear()
            self.assertEqual(first, list(rpc_cache.iter_log_segments(10, 17, {}, max_span=8, url="offline")))
            self.assertEqual(attempts, [])
            self.assertEqual(len(list((Path(tmp) / "data/rpc").glob("*.json"))), 5)

    def test_one_block_failure_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rpc_cache, "ROOT", Path(tmp)), patch.object(rpc_cache, "rpc", side_effect=rpc_cache.RpcError("range too large")) as request:
            with self.assertRaises(rpc_cache.RpcError):
                list(rpc_cache.iter_log_segments(1, 8, {}, max_span=8))
            self.assertEqual(request.call_count, 4)

    def test_non_range_error_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(rpc_cache, "ROOT", Path(tmp)), patch.object(rpc_cache, "rpc", side_effect=rpc_cache.RpcError("Unknown state")) as request:
            with self.assertRaises(rpc_cache.RpcError):
                list(rpc_cache.iter_log_segments(1, 8, {}, max_span=8))
            self.assertEqual(request.call_count, 1)

    def test_block_hash_must_match_returned_log(self):
        with patch.object(rpc_cache, "rpc", side_effect=[{"number": "0x1", "hash": "expected"}, [{"blockHash": "wrong", "blockNumber": "0x1"}]]):
            with self.assertRaisesRegex(rpc_cache.RpcError, "another block"):
                list(rpc_cache.iter_log_segments(1, 1, {}, max_span=1, mode="block_hash"))

    def test_write_method_rejected_before_network(self):
        with patch.object(rpc_transport, "urlopen") as network:
            with self.assertRaises(ValueError):
                rpc_transport.exchange("offline", {"method": "eth_sendRawTransaction"})
            network.assert_not_called()

    def test_concurrent_calls_share_rate_limit(self):
        stamps = []
        with tempfile.TemporaryDirectory() as tmp, patch.object(rpc_transport, "ROOT", Path(tmp)):
            def worker():
                rpc_transport.rate_limit()
                stamps.append(time.monotonic())
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        ordered = sorted(stamps)
        self.assertEqual(len(ordered), 8)
        self.assertTrue(all(b - a >= 0.20 for a, b in zip(ordered, ordered[1:])))
        self.assertTrue(all(ordered[i + 5] - ordered[i] > 1 for i in range(3)))


if __name__ == "__main__":
    unittest.main()
