"""Bounded, cached tests of only the endpoints already authorized in .env."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from phase0_check import ROOT, save
from rpc_cache import rpc
from rpc_transport import STATS, config, exchange, rate_limit, redact, rpc_proxy

SIGNATURE = "LiquidateBorrow(address,address,uint256,address,uint256)"
CDAI = "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"
N = 11330639


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    report_path = ROOT / "data/phase0/rpc_diagnostics.json"
    if report_path.exists() and not args.refresh and json.loads(report_path.read_text(encoding="utf-8" )).get("complete"):
        report = json.loads(report_path.read_text(encoding="utf-8"))
        print(json.dumps({"diagnostic_cache_hit": True, "network_requests": 0, "rows": len(report["tests"])}))
        return
    values = config()
    cast = str(ROOT / ".tools/foundry/cast.exe")
    topic_run = subprocess.run([cast, "keccak", SIGNATURE], capture_output=True, text=True, check=True)
    topic = topic_run.stdout.strip()
    report = {"checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "topic_verification": {"command": "cast keccak " + SIGNATURE, "result": topic},
              "request_format": {"method": "POST", "Content-Type": "application/json", "jsonrpc": "2.0", "id": 1},
              "tests": []}
    url = values["RPCFREE_RPC_URL"]
    metadata, data = exchange(url, {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
    report["rpcfree_urllib"] = metadata
    observations = []
    with rpc_proxy(url, observations) as local:
        run = subprocess.run([cast, "chain-id", "--rpc-url", local], capture_output=True, text=True, timeout=60)
    report["rpcfree_cast"] = {"command": "cast chain-id --rpc-url [redacted RPC; shared rate-limiting proxy]",
                              "returncode": run.returncode, "upstream_observations": observations}
    # Independent cast HTTP-stack check, a single chain-id read, no concurrent
    # calls from this script. Cast also has its conservative local rate cap.
    rate_limit()
    direct = subprocess.run([cast, "chain-id", "--rpc-url", url, "--rpc-timeout", "25",
                             "--compute-units-per-second", "1"], capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=60)
    direct_text = direct.stdout + direct.stderr
    report["rpcfree_cast_direct"] = {"command": "cast chain-id --rpc-url [redacted RPC] --rpc-timeout 25 --compute-units-per-second 1",
                                     "returncode": direct.returncode,
                                     "error_summary": redact(direct_text.splitlines()[0].split("<")[0][:180]) if direct_text else None}
    # The HTML body is discarded; upstream HTTP metadata is recorded above.
    # Do not persist cast's response body, which could include HTML.
    if isinstance(data, dict) and data.get("result") == "0x1" and run.returncode == 0:
        status = json.loads((ROOT / "data/phase0/status.json").read_text())
        oracle = rpc("eth_call", [{"to": status["comptroller"], "data": "0x7dc0d1d0"}, hex(N)], url=url, use_cache=False)
        report["rpcfree_archive"] = {"oracle": "0x" + oracle[-40:], "matches_status": ("0x" + oracle[-40:]).lower() == status["oracle"].lower()}
    save(report_path, report)
    print(json.dumps({k: v for k, v in report.items() if k.startswith("rpcfree")}), flush=True)
    status = json.loads((ROOT / "data/phase0/status.json").read_text())
    block_hash = status["fork_block_hash"]
    endpoints = ["ETH_RPC_URL"] + sorted(k for k in values if k.startswith("CANDIDATE_RPC_"))
    for name in endpoints:
        tests = [("chain", "eth_chainId", [])]
        for span in [500, 1, 10, 50, 100]:
            tests.append((f"range_{span}", "eth_getLogs", [{"address": CDAI, "topics": [topic], "fromBlock": hex(N), "toBlock": hex(N + span - 1)}]))
        for label, filters in [("no_topics", {"address": CDAI}), ("no_address", {"topics": [topic]}), ("no_filters", {})]:
            tests.append((label, "eth_getLogs", [{**filters, "fromBlock": hex(N), "toBlock": hex(N)}]))
        tests.append(("block_hash", "eth_getLogs", [{"address": CDAI, "topics": [topic], "blockHash": block_hash}]))
        tests.append(("historical_block", "eth_getBlockByNumber", [hex(N), False]))
        for label, method, params in tests:
            row = {"endpoint": name, "test": label, "method": method, "params": params}
            try:
                result = rpc(method, params, url=values[name], use_cache=False)
                if method == "eth_getLogs":
                    assert isinstance(result, list)
                    row.update(ok=True, count=len(result))
                elif method == "eth_chainId":
                    row.update(ok=result == "0x1", chain_id=result)
                else:
                    row.update(ok=result["hash"] == block_hash, block_hash=result["hash"])
            except (RuntimeError, AssertionError) as exc:
                row.update(ok=False, error=redact(str(exc) or "Unexpected result shape"))
            report["tests"].append(row)
            save(report_path, report)
            print(json.dumps(row), flush=True)
    working = [r for r in report["tests"] if r["test"].startswith("range_") and r["ok"]]
    if working:
        preferred = next((name for name in endpoints if any(r["endpoint"] == name for r in working)), None)
        span = max(int(r["test"].split("_")[1]) for r in working if r["endpoint"] == preferred)
        save(ROOT / "data/phase0/log_policy.json", {"endpoint_variable": preferred, "mode": "range", "max_span": span, "scope": "maximum tested successful span; not a provider-wide guarantee"})
    else:
        working_hash = [r for r in report["tests"] if r["test"] == "block_hash" and r["ok"] and any(b["endpoint"] == r["endpoint"] and b["test"] == "historical_block" and b["ok"] for b in report["tests"])]
        if working_hash:
            save(ROOT / "data/phase0/log_policy.json", {"endpoint_variable": working_hash[0]["endpoint"], "mode": "block_hash", "max_span": 1, "scope": "blockHash only accepts one block; range mode failed even at one block"})
    report["stats"] = STATS.copy()
    report["complete"] = True
    save(report_path, report)
    print(json.dumps({"complete": True, **STATS}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(redact(exc))
        raise SystemExit(2)
