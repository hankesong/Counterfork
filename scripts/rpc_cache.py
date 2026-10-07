"""Read-only RPC, successful segment caches and adaptive getLogs splitting."""
import hashlib
import json
import os
import re
from pathlib import Path
from phase0_check import ROOT, read_config, save
from rpc_transport import READ_ONLY, STATS, exchange, redact


class RpcError(RuntimeError):
    pass


def rpc(method, params, *, url=None, use_cache=True):
    if method not in READ_ONLY:
        raise ValueError("Method outside the read-only allowlist")
    key = hashlib.sha256(json.dumps([method, params], sort_keys=True).encode()).hexdigest()
    path = Path(os.environ.get("RPC_CACHE_DIR") or ROOT / "data/rpc") / (key + ".json")
    if use_cache and path.exists():
        STATS["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))["result"]
    metadata, result = exchange(url or read_config(), {
        "jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if not isinstance(result, dict):
        raise RpcError(f"{method}: NON_JSON_RESPONSE {metadata}")
    if result.get("error"):
        error = result["error"]
        raise RpcError(redact(f"{method}: RPC error code {error.get('code')}: {error.get('message', '')}")[:600])
    if result.get("jsonrpc") != "2.0" or result.get("id") != 1 or result.get("result") is None:
        raise RpcError(f"{method}: invalid or null response")
    serialized = json.dumps(result["result"])
    if redact(serialized) != serialized:
        raise RpcError("Credential or URL in RPC result; refused to cache")
    save(path, {"method": method, "params": params, "result": result["result"]})
    return result["result"]


def range_error(exc):
    return bool(re.search(r"range|too many|too large|limit exceeded|response size|more than.*blocks", str(exc), re.I))


def iter_log_segments(start, end, filters, *, max_span=None, url=None, mode=None):
    """Yield cached segments; persist successful split layout for offline replay."""
    if start < 0 or end < start or {"fromBlock", "toBlock", "blockHash"} & filters.keys():
        raise ValueError("Invalid range or filters")
    if max_span is None:
        policy_path = ROOT / "data/phase0/log_policy.json"
        if not policy_path.exists():
            raise ValueError("No verified getLogs span; run diagnose_phase0_rpc.py first")
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        max_span = policy["max_span"]
        mode = mode or policy.get("mode", "range")
        if url is None:
            from rpc_transport import config
            url = config()[policy["endpoint_variable"]]
    if mode == "block_hash":
        # A blockHash query has an exact maximum span of one block.
        for n in range(start, end + 1):
            header = rpc("eth_getBlockByNumber", [hex(n), False], url=url)
            if int(header["number"], 16) != n:
                raise RpcError("Historical header number mismatch")
            logs = rpc("eth_getLogs", [{**filters, "blockHash": header["hash"]}], url=url)
            for log in logs:
                if log["blockHash"] != header["hash"] or int(log["blockNumber"], 16) != n:
                    raise RpcError("blockHash query returned a log from another block")
            yield n, n, logs
        return
    if max_span < 1:
        raise ValueError("max_span must be positive")
    identity = hashlib.sha256(json.dumps([start, end, filters, max_span], sort_keys=True).encode()).hexdigest()
    manifest_path = Path(os.environ.get("RPC_CACHE_DIR") or ROOT / "data/rpc") / ("segments_" + identity + ".json")
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"segments": [], "next": start, "span": max_span}
    for segment in manifest["segments"]:
        yield segment[0], segment[1], rpc("eth_getLogs", [{**filters, "fromBlock": hex(segment[0]), "toBlock": hex(segment[1])}], url=url)
    cursor, span = manifest["next"], manifest["span"]
    while cursor <= end:
        stop = min(end, cursor + span - 1)
        try:
            logs = rpc("eth_getLogs", [{**filters, "fromBlock": hex(cursor), "toBlock": hex(stop)}], url=url)
        except RpcError as exc:
            if not range_error(exc) or stop == cursor:
                raise
            span = max(1, (stop - cursor + 1) // 2)
            manifest["span"] = span
            save(manifest_path, manifest)
            continue
        manifest["segments"].append([cursor, stop])
        manifest.update(next=stop + 1, span=span)
        save(manifest_path, manifest)
        yield cursor, stop, logs
        cursor = stop + 1
