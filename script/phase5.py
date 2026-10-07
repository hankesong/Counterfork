"""Phase 5 tools: local E2E, cache-only regression, mainnet read-only preflight,
and explicitly authorized chain-968 rehearsal. Python standard library only.
Never prints subprocess command lines, private keys, or credential-bearing URLs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".tools/foundry"
SECRETS = []
GAS_PRICE = 20_000_000_000
SUBMIT = "submitInvestigation(bytes32,uint256,uint256,uint256,bytes32,string)"
ATTEST = "attestReproduction(bytes32,uint256,bool,bytes32)"
INVESTIGATION = "getInvestigation(bytes32,uint256)((address,uint256,uint256,uint256,bytes32,string,uint256,uint256))"
ATTESTATION = "getAttestation(bytes32,uint256,uint256)((address,bool,bytes32,uint256,uint256))"


def config():
    values = {}
    path = ROOT / ".env"
    for line in path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []:
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    values.update({k: v for k, v in os.environ.items() if k.startswith("BOT_")})
    SECRETS.extend(v for k, v in values.items() if v and ("KEY" in k or "RPC" in k))
    return values


def redact(text):
    for secret in sorted(set(SECRETS), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    return re.sub(r"https?://[^\s\"<>]+", "[RPC URL]", text)


def environment(key=None):
    env = os.environ.copy()
    # Do not inherit unrelated ETH RPC or signing options into BOT Chain commands.
    for name in list(env):
        if name.startswith(("ETH_", "FOUNDRY_", "DAPP_")) or name in ("CHAIN", "PRIVATE_KEY"):
            env.pop(name)
    env.update(FOUNDRY_PROFILE="botchain", NO_COLOR="1")
    if key is not None:
        env["BOT_PRIVATE_KEY"] = key
    return env


def run(tool, *args, env=None, cwd=ROOT, timeout=120):
    exe = TOOLS / (tool + ".exe")
    try:
        result = subprocess.run([str(exe), *map(str, args)], cwd=cwd,
                                env=env or environment(), capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{tool} timed out; inspect saved transaction journal before retrying") from None
    if result.returncode:
        raise RuntimeError(redact(result.stdout + result.stderr)) from None
    return result.stdout.strip()


def save(name, result):
    result["recorded_at_utc"] = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if any(secret in encoded for secret in SECRETS if secret):
        raise RuntimeError("Refusing to persist a secret")
    path = ROOT / "deployments" / name
    path.parent.mkdir(exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def number(value):
    return int(str(value), 16) if str(value).startswith("0x") else int(value)


def wallet(key):
    # Key goes directly to a captured child process, never to a shell or log.
    # Do not enable shell tracing or dump child argv/environment.
    return run("cast", "wallet", "address", "--private-key", key)


def chain(rpc, expected):
    actual = int(run("cast", "chain-id", "--rpc-url", rpc))
    if actual != expected:
        raise RuntimeError(f"Chain mismatch: expected {expected}, received {actual}; stopped")
    return actual


def preflight(values):
    rpc = values.get("BOT_RPC_URL", "")
    if not rpc or values.get("BOT_CHAIN_ID") != "677":
        raise RuntimeError("BOT_RPC_URL and BOT_CHAIN_ID=677 must be configured")
    report = {"purpose": "BOT Chain mainnet read-only preflight; no broadcast", "broadcast": False,
              "chain_id": chain(rpc, 677), "gas_price_wei": GAS_PRICE}
    key = values.get("BOT_PRIVATE_KEY")
    if not key:
        report.update(status="skipped_balance_and_simulation", reason="BOT_PRIVATE_KEY is empty")
    else:
        report["deployer"] = wallet(key)
        balance = int(run("cast", "balance", report["deployer"], "--rpc-url", rpc))
        report.update(balance_wei=str(balance), balance_native=str(Decimal(balance) / 10**18))
        # Deliberately no --broadcast option; this function has no sending code.
        output = run("forge", "script", "script/DeployRegistry.s.sol", "--rpc-url", rpc,
                     "--legacy", "--gas-price", GAS_PRICE, env=environment(key), timeout=240)
        match = re.search(r"Estimated total gas used for script:\s*([\d,]+)", output)
        if not match:
            raise RuntimeError("Simulation returned no gas estimate: " + redact(output))
        gas = int(match[1].replace(",", ""))
        fee = gas * GAS_PRICE
        report.update(status="simulated_only", estimated_gas=gas, estimated_fee_wei=str(fee),
                      estimated_fee_native=str(Decimal(fee) / 10**18), balance_sufficient=balance >= fee,
                      simulation_output=redact(output))
    save("botchain-preflight.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def check_event(receipt, contract, signature, case_id, expected_data):
    topic = run("cast", "keccak", signature)
    logs = receipt["logs"]
    if len(logs) != 1:
        raise RuntimeError("Expected exactly one registry event")
    log = logs[0]
    if (log["address"].lower() != contract.lower() or
            [x.lower() for x in log["topics"]] != [topic.lower(), case_id.lower()] or
            log["data"].lower() != expected_data.lower()):
        raise RuntimeError("Event topic/emitter/data mismatch")
    return {"signature": signature, "topic0": topic, "caseId": case_id,
            "indexed_fields": ["caseId"], "verified": True}


def receipt(rpc, tx):
    result = json.loads(run("cast", "receipt", tx, "--rpc-url", rpc, "--json", timeout=180))
    if number(result["status"]) != 1:
        raise RuntimeError("Transaction reverted: " + tx)
    return result


def rehearsal(rpc, expected, key, filename, explorer=None):
    if expected not in (31337, 968):
        raise RuntimeError("Rehearsal may only broadcast on local chain 31337 or testnet 968")
    path = ROOT / "deployments" / filename
    if expected == 968 and path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("deployment") or existing.get("transactions"):
            raise RuntimeError("Existing testnet deployment/journal: inspect it before any repeat broadcast")
    chain(rpc, expected)
    sender = wallet(key)
    balance = int(run("cast", "balance", sender, "--rpc-url", rpc))
    report = {"purpose": "测试网彩排，不是比赛有效部署" if expected == 968 else "Local Anvil TEST ONLY",
              "chain_id": expected, "deployer": sender, "starting_balance_wei": str(balance),
              "status": "checked", "transactions": {}}
    if explorer:
        report["explorer"] = explorer
    save(filename, report)
    if balance == 0:
        report.update(status="blocked_no_testnet_funds", reason="Deployment address has zero testnet balance")
        save(filename, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    chain(rpc, expected)
    run("forge", "script", "script/DeployRegistry.s.sol", "--rpc-url", rpc,
        "--chain", expected, "--legacy", "--gas-price", GAS_PRICE, "--broadcast",
        env=environment(key), timeout=240)
    artifact = ROOT / "out-botchain/broadcast/DeployRegistry.s.sol" / str(expected) / "run-latest.json"
    broadcast = json.loads(artifact.read_text(encoding="utf-8"))
    deployment = receipt(rpc, broadcast["transactions"][0]["hash"])
    contract = deployment["contractAddress"]
    if not contract or run("cast", "code", contract, "--rpc-url", rpc) == "0x":
        raise RuntimeError("Deployment has no code")
    report.update(contract=contract, deployment=deployment, status="deployed")
    save(filename, report)
    case_id = run("cast", "keccak", "compound-2020-11-26-dai")
    manifest = run("cast", "keccak", "TEST ONLY: phase5 rehearsal manifest; not an investigation")
    result_hash = run("cast", "keccak", "TEST ONLY: phase5 rehearsal result; not independent evidence")
    uri = "https://example.invalid/TEST-ONLY/phase5-manifest.json"
    report["test_parameters"] = {"caseId": case_id, "targetChainId": 1, "fromBlock": 100,
                                 "toBlock": 200, "manifestHash": manifest, "manifestURI": uri,
                                 "matched": True, "resultHash": result_hash, "version": 1}
    for label, signature, args in [
        ("submit", SUBMIT, [case_id, 1, 100, 200, manifest, uri]),
        ("attest", ATTEST, [case_id, 1, "true", result_hash]),
    ]:
        chain(rpc, expected)
        tx = run("cast", "send", contract, signature, *args, "--rpc-url", rpc,
                 "--chain", expected, "--private-key", key, "--legacy", "--gas-price", "20gwei", "--async")
        report["transactions"][label] = {"transactionHash": tx}
        save(filename, report)  # Journal immediately, before receipt polling.
        report["transactions"][label] = receipt(rpc, tx)
        save(filename, report)
    readback = {
        "latestVersion": run("cast", "call", contract, "latestVersion(bytes32)(uint256)", case_id, "--rpc-url", rpc),
        "investigation": run("cast", "call", contract, INVESTIGATION, case_id, 1, "--rpc-url", rpc),
        "attestationCount": run("cast", "call", contract, "attestationCount(bytes32,uint256)(uint256)", case_id, 1, "--rpc-url", rpc),
        "attestation": run("cast", "call", contract, ATTESTATION, case_id, 1, 0, "--rpc-url", rpc),
        "hasAttested": run("cast", "call", contract, "hasAttested(bytes32,uint256,address)(bool)", case_id, 1, sender, "--rpc-url", rpc),
    }
    if readback["latestVersion"] != "1" or readback["attestationCount"] != "1" or readback["hasAttested"] != "true":
        raise RuntimeError("Readback count/membership mismatch")
    # Compare complete ABI encodings, including block number and timestamp.
    for label, getter, getter_args, encoding, fields in [
        ("submit", INVESTIGATION.split("(", 1)[0] + "(bytes32,uint256)", [case_id, 1],
         "f((address,uint256,uint256,uint256,bytes32,string,uint256,uint256))",
         [sender, 1, 100, 200, manifest, uri]),
        ("attest", "getAttestation(bytes32,uint256,uint256)", [case_id, 1, 0],
         "f((address,bool,bytes32,uint256,uint256))", [sender, "true", result_hash]),
    ]:
        tx_receipt = report["transactions"][label]
        block = json.loads(run("cast", "rpc", "eth_getBlockByNumber", tx_receipt["blockNumber"], "false", "--rpc-url", rpc))
        fields += [number(block["timestamp"]), number(tx_receipt["blockNumber"])]
        expected_abi = run("cast", "abi-encode", encoding, "(" + ",".join(map(str, fields)) + ")")
        actual_abi = run("cast", "call", contract, getter, *getter_args, "--rpc-url", rpc)
        if actual_abi.lower() != expected_abi.lower():
            raise RuntimeError("Full record ABI mismatch: " + label)
    report["events"] = [
        check_event(report["transactions"]["submit"], contract,
                    "InvestigationSubmitted(bytes32,uint256,address,bytes32)", case_id,
                    run("cast", "abi-encode", "f(uint256,address,bytes32)", 1, sender, manifest)),
        check_event(report["transactions"]["attest"], contract,
                    "ReproductionAttested(bytes32,uint256,address,bool)", case_id,
                    run("cast", "abi-encode", "f(uint256,address,bool)", 1, sender, "true")),
    ]
    report.update(status="verified", readback=readback, complete_record_abi_verified=True,
                  ending_balance_wei=run("cast", "balance", sender, "--rpc-url", rpc))
    save(filename, report)
    print(json.dumps({k: report[k] for k in ("purpose", "chain_id", "deployer", "contract", "status", "readback", "events")},
                     ensure_ascii=False, indent=2))
    for label, item in report["transactions"].items():
        print(label, item["transactionHash"], "status", item["status"], "gasUsed", number(item["gasUsed"]))


def local():
    # Capture Anvil's generated startup credentials only in memory; never persist them.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    proc = subprocess.Popen([str(TOOLS / "anvil.exe"), "--host", "127.0.0.1", "--port", str(port),
                             "--chain-id", "31337"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, env=environment(), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    keys = []

    def consume():
        for line in proc.stdout:
            match = re.match(r"\(0\)\s+(0x[0-9a-fA-F]{64})\s*$", line.strip())
            if match:
                keys.append(match[1])

    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    try:
        deadline = time.monotonic() + 15
        while not keys and time.monotonic() < deadline and proc.poll() is None:
            time.sleep(0.1)
        if not keys:
            raise RuntimeError("Could not obtain Anvil default test account from captured startup")
        SECRETS.append(keys[0])
        rehearsal(f"http://127.0.0.1:{port}", 31337, keys[0], "anvil-phase5.json")
    finally:
        proc.terminate()
        proc.wait(timeout=15)
        reader.join(timeout=2)
        print("Anvil stopped")


def regression():
    """No upstream transport exists. Cache misses fail closed. All writes isolated."""
    stats = {"cache_hits": 0, "cache_misses": [], "upstream_requests": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            method, params = payload["method"], payload.get("params", [])
            digest = hashlib.sha256(json.dumps([method, params], sort_keys=True).encode()).hexdigest()
            path = ROOT / "data/rpc" / (digest + ".json")
            data = {"jsonrpc": "2.0", "id": payload.get("id")}
            if path.exists():
                stats["cache_hits"] += 1
                data["result"] = json.loads(path.read_text(encoding="utf-8"))["result"]
            else:
                stats["cache_misses"].append({"method": method, "params": params})
                data["error"] = {"code": -32000, "message": "OFFLINE cache miss; no upstream allowed"}
            encoded = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sample = json.loads((ROOT / "data/phase1/sample.json").read_text(encoding="utf-8"))
        prices = json.loads((ROOT / "data/phase1/price_evidence.json").read_text(encoding="utf-8"))
        env = environment()
        env.update(FOUNDRY_PROFILE="default", ETH_RPC_URL=f"http://127.0.0.1:{server.server_port}",
                   PHASE1_BLOCK=str(sample["fork_block"]), PHASE1_TIMESTAMP=str(sample["fork_timestamp"]),
                   PHASE1_COMPTROLLER="0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b",
                   PHASE1_CDAI="0x5d3a536e4d6dbd6114cc1ead35777bab948e3643", PHASE1_BORROWER=sample["borrower"],
                   PHASE1_ORACLE=prices["oracle"], PHASE1_DAI=prices["dai"],
                   PHASE1_REFERENCE_PRICE=prices["reference_price_raw"], PHASE1_ACTUAL_PRICE=prices["actual_price_raw"],
                   PHASE1_DIAGNOSTIC_COUNT=str(len(prices["diagnostic_prices"])))
        for i, price in enumerate(prices["diagnostic_prices"]):
            env[f"PHASE1_MARKET_{i}"] = price["market"]
            env[f"PHASE1_PRICE_{i}"] = price["price_raw"]
        with tempfile.TemporaryDirectory(prefix="phase5-offline-") as folder:
            temp = Path(folder)
            for directory in ("test", ".tools", "data/phase1"):
                (temp / directory).mkdir(parents=True)
            for file in ("foundry.toml", "test/Phase1.t.sol", ".tools/solc.exe"):
                shutil.copy2(ROOT / file, temp / file)
            output = run("forge", "test", "--match-path", "test/Phase1.t.sol", "-vv", "--offline",
                         env=env, cwd=temp, timeout=180)
            observed = json.loads((temp / "data/phase1/fork_result.json").read_text(encoding="utf-8"))
            previous = json.loads((ROOT / "data/phase1/fork_result.json").read_text(encoding="utf-8"))
            if observed != previous:
                raise RuntimeError("Offline regression differs from historical fork_result")
        report = {"status": "passed", "profile": "default", "evm_version": "istanbul",
                  "historical_result_identical": True, **stats, "output": output}
        save("phase1-offline-regression.json", report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["local", "regression", "preflight", "testnet"])
    args = parser.parse_args()
    values = config()
    if args.mode == "local":
        local()
    elif args.mode == "regression":
        regression()
    elif args.mode == "preflight":
        preflight(values)
    else:
        rpc = values.get("BOT_TESTNET_RPC_URL") or "https://rpc.bohr.life"
        if (values.get("BOT_TESTNET_CHAIN_ID") or "968") != "968":
            raise RuntimeError("BOT_TESTNET_CHAIN_ID must be 968")
        chain(rpc, 968)  # Validate even if the signing key is missing.
        key = values.get("BOT_PRIVATE_KEY")
        if not key:
            save("botchain-testnet.json", {"purpose": "测试网彩排，不是比赛有效部署", "chain_id": 968,
                                          "status": "blocked_missing_private_key"})
            print("Testnet chain 968 confirmed; BOT_PRIVATE_KEY is empty, rehearsal skipped")
            return
        rehearsal(rpc, 968, key, "botchain-testnet.json",
                  values.get("BOT_TESTNET_EXPLORER_URL") or "https://scan.bohr.life")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("ERROR:", redact(str(error)))
        raise SystemExit(1) from None
