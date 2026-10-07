"""Bounded read-only discovery; never print configured endpoints."""
import json
from urllib.request import Request, urlopen
from phase0_check import ROOT, save
from rpc_cache import rpc
from rpc_transport import config, redact, STATS
from locate_phase0_sample import CDAI, TOPIC


def main():
    folder = ROOT / 'data/phase1'
    folder.mkdir(exist_ok=True)
    path = folder / 'discovery.json'
    report = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'probes': [], 'web': []}
    for name, url in config().items():
        if name != 'ETH_RPC_URL' and not name.startswith('CANDIDATE_RPC_'):
            continue
        for span in (1, 50):
            if any(r['endpoint'] == name and r['span'] == span for r in report['probes']):
                continue
            row = {'endpoint': name, 'span': span}
            try:
                logs = rpc('eth_getLogs', [{'address': CDAI, 'topics': [TOPIC],
                    'fromBlock': hex(11333058), 'toBlock': hex(11333058 + span - 1)}], url=url, use_cache=False)
                row.update(ok=True, logs=logs)
            except Exception as exc:
                row.update(ok=False, error=redact(exc))
            report['probes'].append(row)
            save(path, report)
            print(json.dumps(row), flush=True)
    pages = {
        'bing': 'https://www.bing.com/search?q=compound+2020+%2246%22+%22etherscan%22',
        'theblock': 'https://www.theblock.co/post/85850/dai-compound-dydx-liquidations-defi',
        'search': 'https://www.google.com/search?q=Compound+November+26+2020+46+million+liquidation+etherscan',
        'etherscan_cdai': 'https://etherscan.io/txs?a=' + CDAI + '&startblock=11330639&endblock=11337150&ps=100',
        'invezz': 'https://invezz.com/news/2020/11/27/increased-dai-price-allowed-compound-comp-liquidator-to-earn-4-million/',
        'decrypt': 'https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound',
    }
    for label, url in pages.items():
        if any(r['label'] == label for r in report['web']):
            continue
        row = {'label': label, 'source': url}
        try:
            with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=25) as response:
                body = response.read().decode(errors='replace')
            private = ROOT / 'data/private'
            private.mkdir(parents=True, exist_ok=True)
            (private / (label + '.html')).write_text(body, encoding='utf-8')
            row.update(ok=True)
        except Exception as exc:
            row.update(ok=False, error=redact(exc))
        report['web'].append(row)
        save(path, report)
        print(redact(json.dumps(row)), flush=True)
    print(json.dumps(STATS))


if __name__ == '__main__':
    main()
