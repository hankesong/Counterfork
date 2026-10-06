"""Phase 0: cached historical RPC + actual Foundry fork verification.

This environment smoke test uses a verified November 2020 block, not a claimed
pre-liquidation state. Phase 1 must select a real liquidation and use its N-1.
Use --retry-rpc only to retry a previously failed connectivity check.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from rpc_transport import exchange, redact, rpc_proxy

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "data" / "phase0" / "status.json"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def read_config():
    path = ROOT / ".env"
    if not path.exists():
        raise ValueError("Create .env from .env.example and configure ETH_RPC_URL.")
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    url = values.get("ETH_RPC_URL", "")
    if not url.startswith(("https://", "http://")):
        raise ValueError("ETH_RPC_URL is missing or invalid in .env.")
    return url


def tool_version(name):
    local = ROOT / ".tools" / "foundry" / (name + (".exe" if os.name == "nt" else ""))
    executable = str(local) if local.exists() else shutil.which(name)
    if not executable:
        return {"available": False}
    result = subprocess.run([executable, "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
    return {"available": result.returncode == 0, "version": result.stdout.strip()}


def probe(url):
    payload = {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1}
    record = {"checked_at_utc": datetime.now(timezone.utc).isoformat(), "request": payload}
    try:
        metadata, data = exchange(url, payload)
        record.update(metadata)
        if data is None:
            record.update(ok=False, error="NON_JSON_RESPONSE")
            return record
        if not isinstance(data, dict) or data.get("jsonrpc") != "2.0" or data.get("id") != 1:
            record.update(ok=False, error="INVALID_JSON_RPC_RESPONSE")
        elif "error" in data:
            error = data["error"]
            record.update(ok=False, error="RPC_ERROR", rpc_error_code=error.get("code") if isinstance(error, dict) else None)
        elif data.get("result") != "0x1":
            record.update(ok=False, error="NOT_ETHEREUM_MAINNET")
        else:
            record.update(ok=True, chain_id=1)
    except HTTPError as exc:
        record.update(ok=False, error="HTTP_ERROR", http_status=exc.code)
    except (RuntimeError, URLError, TimeoutError, OSError) as exc:
        record.update(ok=False, error=redact(exc))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--retry-rpc", action="store_true", help="Retry a failed probe; successful caches are reused.")
    args = parser.parse_args()
    if RESULT.exists():
        previous = json.loads(RESULT.read_text(encoding="utf-8"))
        if previous.get("status") == "passed" and previous.get("implementation_sha256") == implementation_hash():
            print(json.dumps({**previous, "result_cache_hit": True, "rpc_requests_this_run": 0}, ensure_ascii=False, indent=2))
            return 0
    url = read_config()
    key = hashlib.sha256(url.encode()).hexdigest()
    path = ROOT / "data" / "private" / "rpc" / (key + ".json")
    cached = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    hit = cached is not None and (cached.get("ok") or not args.retry_rpc)
    check = cached if hit else probe(url)
    if not hit:
        save(path, check)
    result = {
        "phase": 0, "status": "blocked" if not check["ok"] else "pending_archive_and_fork",
        "python": sys.version.split()[0], "forge": tool_version("forge"), "cast": tool_version("cast"),
        "rpc_probe": {**check, "cache_hit": hit},
        "archive_verified": False, "foundry_fork_verified": False,
        "liquidation_transaction": None, "fork_block": None,
        "oracle": None, "dai_price_raw": None, "dai_price_usd": None,
    }
    if check["ok"]:
        try:
            result.update(verify_archive_and_fork(url))
        except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
            result.update(status="blocked", failure=str(exc).replace(url, "[redacted RPC]"))
    save(RESULT, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


def implementation_hash():
    files = [Path(__file__), ROOT / "scripts/rpc_cache.py", ROOT / "scripts/rpc_transport.py", ROOT / "test/Phase0.t.sol", ROOT / "foundry.toml"]
    return hashlib.sha256(b"".join(path.read_bytes() for path in files)).hexdigest()


def verify_archive_and_fork(url):
    from rpc_cache import rpc
    comptroller = "0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B"
    cdai = "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"
    n = 11330639  # Binary search of timestamp; raw block responses are cached.
    block = rpc("eth_getBlockByNumber", [hex(n), False])
    stamp = int(block["timestamp"], 16)
    date = datetime.fromtimestamp(stamp, timezone.utc)
    if date.date().isoformat() != "2020-11-26":
        raise RuntimeError("Historical block is outside the intended date")
    raw_oracle = rpc("eth_call", [{"to": comptroller, "data": "0x7dc0d1d0"}, hex(n)])
    if not re.fullmatch(r"0x[0-9a-fA-F]{64}", raw_oracle) or int(raw_oracle, 16) == 0:
        raise RuntimeError("Invalid historical oracle address")
    oracle = "0x" + raw_oracle[-40:]
    raw_price = rpc("eth_call", [{"to": oracle, "data": "0xfc57d4df" + "0" * 24 + cdai[2:].lower()}, hex(n)])
    price = int(raw_price, 16)
    if price <= 0:
        raise RuntimeError("Invalid historical DAI price")
    env = os.environ.copy()
    env.update(ETH_RPC_URL=url, PHASE0_BLOCK=str(n), PHASE0_TIMESTAMP=str(stamp), PHASE0_COMPTROLLER=comptroller, PHASE0_CDAI=cdai)
    forge = ROOT / ".tools/foundry/forge.exe"
    command = [str(forge) if forge.exists() else "forge", "test", "--match-contract", "Phase0Test", "-vv"]
    # Delete only this generated output to rule out an old successful fork file.
    fork_path = ROOT / "data/phase0/fork_read.json"
    fork_path.unlink(missing_ok=True)
    with rpc_proxy(url) as local:
        env["ETH_RPC_URL"] = local
        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    log = redact(run.stdout + run.stderr)
    log = re.sub(r"https?://[^\s\"<>]+", "[redacted URL]", log)
    save(ROOT / "data/phase0/forge_run.json", {"returncode": run.returncode, "output": log})
    if run.returncode != 0 or not fork_path.exists():
        raise RuntimeError("Foundry fork failed; see data/phase0/forge_run.json")
    fork = json.loads(fork_path.read_text(encoding="utf-8"))
    if fork["oracle"].lower() != oracle.lower() or int(fork["dai_price_raw"]) != price or fork["block"] != n or fork["timestamp"] != stamp:
        raise RuntimeError("Foundry result differs from historical eth_call or block header")
    return {"status": "passed", "archive_verified": True, "foundry_fork_verified": True,
            "verification_kind": "historical_environment_smoke_test_not_pre_liquidation",
            "comptroller": comptroller, "cdai": cdai, "fork_block": n, "fork_block_hash": block["hash"],
            "fork_timestamp_utc": date.isoformat(), "oracle": oracle, "underlying": fork["underlying"],
            "underlying_decimals": fork["underlying_decimals"], "dai_price_raw": str(price),
            "dai_price_usd": format(Decimal(price) / Decimal(10**18), "f"),
            "implementation_sha256": implementation_hash(), "result_cache_hit": False,
            "limitations": ["This fork is an environment check; the separately verified sample is in data/phase0/sample.json. Phase 1 must use its N-1.",
                            "A successful archive read does not establish historical getLogs availability."]}


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
