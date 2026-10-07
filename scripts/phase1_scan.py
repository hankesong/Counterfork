"""Bounded incident-window search using the verified blockHash log mode."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from phase0_check import ROOT, save
from rpc_cache import rpc, iter_log_segments
from rpc_transport import STATS, redact
from locate_phase0_sample import CDAI, TOPIC, block


def first_at(stamp):
    lo, hi = 11330639, 11370000
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if int(block(mid)['timestamp'], 16) < stamp:
            lo = mid
        else:
            hi = mid
    return hi


def main():
    path = ROOT / 'data/phase1/search_logs.json'
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'logs': [], 'checked': []}
    started = time.monotonic()
    day = int(datetime(2020, 11, 26, tzinfo=timezone.utc).timestamp())
    start, end = first_at(day + 8 * 3600), first_at(day + 10 * 3600) - 1
    report.update(start=start, end=end, scope='08:00–10:00 UTC incident window; not whole day')
    def scan(n):
        return next(iter_log_segments(n, n, {'address': CDAI, 'topics': [TOPIC]}, mode='block_hash'))
    todo = [n for n in range(start, end + 1) if n not in report['checked']]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i in range(0, len(todo), 24):
            if time.monotonic() - started > 900:
                raise RuntimeError('15-minute incident-window search deadline reached')
            for n, _, logs in pool.map(scan, todo[i:i+24]):
                report['checked'].append(n)
                report['logs'].extend(logs)
            save(path, report)
            ranked = sorted(report['logs'], key=lambda x: int(x['data'][130:194], 16), reverse=True)
            print(json.dumps({'checked': len(report['checked']), 'logs': len(ranked),
                'largest_repay_raw': str(int(ranked[0]['data'][130:194], 16)) if ranked else None,
                **STATS}), flush=True)
    report['complete'] = True
    save(path, report)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        save(ROOT / 'data/phase1/search_error.json', {'error': redact(exc)})
        print(redact(exc))
        raise SystemExit(2)
