"""Locate one cDAI liquidation on 2020-11-26 UTC, stopping at first match."""
from datetime import datetime, timezone
import json
import time
from concurrent.futures import ThreadPoolExecutor
from phase0_check import ROOT, save
from rpc_cache import rpc, iter_log_segments
from rpc_transport import STATS, redact

COMPTROLLER = "0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B"
CDAI = "0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643"
TOPIC = "0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"


def block(n):
    return rpc("eth_getBlockByNumber", [hex(n), False])


def main():
    sample_path = ROOT / "data" / "phase0" / "sample.json"
    started = time.monotonic()
    target = int(datetime(2020, 11, 26, tzinfo=timezone.utc).timestamp())
    lo, hi = 11300000, 11370000
    assert int(block(lo)["timestamp"], 16) < target <= int(block(hi)["timestamp"], 16)
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if int(block(mid)["timestamp"], 16) < target:
            lo = mid
        else:
            hi = mid
    print(f"First block on 2020-11-26 UTC: {hi}", flush=True)
    # Find the exact UTC-day end, avoiding guesses about daily block count.
    lo_end, hi_end = hi, 11370000
    while lo_end + 1 < hi_end:
        mid = (lo_end + hi_end) // 2
        if int(block(mid)["timestamp"], 16) < target + 86400:
            lo_end = mid
        else:
            hi_end = mid
    end = lo_end
    # Search the reported incident's morning window first; this is not an
    # assertion that the first event of the UTC day occurred in this window.
    window_lo, window_hi = hi, end
    morning = target + 9 * 3600
    while window_lo + 1 < window_hi:
        mid = (window_lo + window_hi) // 2
        if int(block(mid)["timestamp"], 16) < morning:
            window_lo = mid
        else:
            window_hi = mid
    day_start = hi
    hi = window_hi
    if sample_path.exists():
        previous = json.loads(sample_path.read_text())
        end = previous["liquidation_block"]
    filters = {"address": CDAI, "topics": [TOPIC]}
    policy = json.loads((ROOT / "data/phase0/log_policy.json").read_text())

    def scan(n):
        return next(iter_log_segments(n, n, filters))

    def segments():
        if policy["mode"] == "range":
            yield from iter_log_segments(hi, end, filters)
        else:
            # Bounded parallel HTTP waits; all request starts share the global limiter.
            with ThreadPoolExecutor(max_workers=8) as pool:
                for start in range(hi, end + 1, 24):
                    if time.monotonic() - started > 900:
                        raise RuntimeError("15-minute bounded sample search expired; keep caches and report alternatives")
                    yield from pool.map(scan, range(start, min(start + 24, end + 1)))

    segment_iterator = segments()
    for start, stop, logs in segment_iterator:
        if (start - hi) % 24 == 0 or logs:
            print(f"Checked through {stop}: {len(logs)} cDAI liquidation logs in this segment", flush=True)
        if not logs:
            continue
        segment_iterator.close()  # Join bounded prefetch before reporting counters.
        event = min(logs, key=lambda e: (int(e["blockNumber"], 16), int(e["logIndex"], 16)))
        n = int(event["blockNumber"], 16)
        event_block, fork_block = block(n), block(n - 1)
        assert target <= int(event_block["timestamp"], 16) < target + 86400
        receipt = rpc("eth_getTransactionReceipt", [event["transactionHash"]])
        assert receipt["status"] == "0x1"
        assert receipt["transactionHash"] == event["transactionHash"]
        assert receipt["blockHash"] == event_block["hash"] == event["blockHash"]
        assert int(receipt["blockNumber"], 16) == n
        assert event["topics"] == [TOPIC] and not event.get("removed", False)
        assert event["address"].lower() == CDAI.lower()
        assert any(all(log[key] == event[key] for key in ("logIndex", "data", "topics", "blockHash", "blockNumber", "transactionHash")) and log["address"].lower() == CDAI.lower() for log in receipt["logs"])
        words = [event["data"][2 + i * 64:2 + (i + 1) * 64] for i in range(5)]
        assert len(event["data"]) == 2 + 5 * 64
        result = {"comptroller": COMPTROLLER, "cdai": CDAI, "liquidation_transaction": event["transactionHash"], "liquidation_block": n,
                  "liquidation_timestamp_utc": datetime.fromtimestamp(int(event_block["timestamp"], 16), timezone.utc).isoformat(),
                  "fork_block": n - 1, "fork_block_hash": fork_block["hash"], "fork_timestamp": int(fork_block["timestamp"], 16),
                  "fork_timestamp_utc": datetime.fromtimestamp(int(fork_block["timestamp"], 16), timezone.utc).isoformat(),
                  "search_start_block": hi, "utc_day_start_block": day_start,
                  "selection": "one verified event at or after 09:00 UTC; not claimed to be the first event of the day",
                  "liquidator": "0x" + words[0][-40:], "borrower": "0x" + words[1][-40:],
                  "repayAmount": str(int(words[2], 16)), "cTokenCollateral": "0x" + words[3][-40:],
                  "seizeTokens": str(int(words[4], 16)), "receipt_status": receipt["status"], "receipt_log_verified": True,
                  "log": event, "source": "Ethereum mainnet receipt and LiquidateBorrow log; only one sample selected"}
        save(sample_path, result)
        print(f"Verified sample: block {n}, transaction {event['transactionHash']}")
        print(json.dumps(STATS), flush=True)
        runs_path = ROOT / "data/phase0/sample_runs.json"
        runs = json.loads(runs_path.read_text(encoding="utf-8")) if runs_path.exists() else []
        runs.append({"checked_at_utc": datetime.now(timezone.utc).isoformat(), **STATS,
                     "receipt_verified": True, "transaction": event["transactionHash"]})
        save(runs_path, runs)
        return
    raise RuntimeError("No sample found in bounded search")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(redact(exc))
        raise SystemExit(2)
