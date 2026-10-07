"""Output-only derivations and fail-closed evidence provenance checks."""
from datetime import datetime, timezone
from phase0_check import ROOT, save
from phase1_single import load

SOURCE = 'Ethereum mainnet via cached eth_getLogs/eth_call'
MODES = {'LIVE', 'FROZEN', 'UI_MOCK'}


def require_evidence(document, name):
    def reject_nested_mock(value):
        if isinstance(value, dict):
            if value.get('mode') == 'UI_MOCK':
                raise ValueError(name + ': UI_MOCK data must not be used as evidence')
            for child in value.values():
                reject_nested_mock(child)
        elif isinstance(value, list):
            for child in value:
                reject_nested_mock(child)
    reject_nested_mock(document)
    if not isinstance(document, dict) or not isinstance(document.get('provenance'), dict):
        raise ValueError(name + ': missing provenance')
    proof = document['provenance']
    if proof.get('mode') not in MODES:
        raise ValueError(name + ': invalid provenance.mode')
    if proof['mode'] == 'UI_MOCK':
        raise ValueError(name + ': UI_MOCK data must not be used as evidence')
    if proof.get('source') != SOURCE:
        raise ValueError(name + ': unrecognized provenance.source')
    stamp = datetime.fromisoformat(proof['capturedAt'].replace('Z', '+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError(name + ': capturedAt must be UTC ISO')


def provenance(folder, network_requests, current_run=None):
    path = folder / 'provenance_origin.json'
    if path.exists():
        origin = load(path)
    else:
        runs = load(folder / 'runs.json') if (folder / 'runs.json').exists() else []
        if current_run is not None:
            runs = runs + [current_run]
        candidates = [r for r in runs if any(s['stage'] == 'logs' and int(s['rpc_requests']) > 0
                                             for s in r['stages'])]
        if not candidates:
            raise ValueError('No recorded initial acquisition time; refusing to invent capturedAt')
        first = min(candidates, key=lambda r: datetime.fromisoformat(r['started_utc']))
        captured = datetime.fromisoformat(first['started_utc']).astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        origin = {'capturedAt': captured, 'basis': 'Earliest recorded Phase 2 full-day acquisition run started_utc in runs.json; initial preparation had no timestamp; not per-request cache creation time.'}
        save(path, origin)
    proof = {'mode': 'LIVE' if network_requests else 'FROZEN', 'source': SOURCE,
             'capturedAt': origin['capturedAt']}
    require_evidence({'provenance': proof}, 'generated output')
    return proof


def analyzed_borrowers(path=None):
    default_path = path is None
    phase3 = set()
    batch = ROOT / 'data/phase3/experiments.json'
    if default_path and batch.exists():
        document = load(batch)
        require_evidence(document, 'Phase 3 experiments')
        for row in document['experiments']:
            require_evidence(row, 'Phase 3 account')
            if row['status'] == 'passed':
                real = row['groups']['real']
                if real['err'] != '0' or int(real['shortfall']) <= 0:
                    raise ValueError('Invalid Phase 3 passed account')
                phase3.add(row['borrower'].lower())
    path = path if path is not None else ROOT / 'data/phase1/single_account.json'
    if not path.exists():
        return phase3
    result = load(path)
    real = result.get('groups', {}).get('real', {})
    borrower = result.get('borrower')
    try:
        accepted = (result.get('status') == 'passed' and real.get('err') == '0'
                    and int(real.get('shortfall', '0')) > 0 and isinstance(borrower, str)
                    and borrower == result.get('sample', {}).get('borrower'))
    except (ValueError, TypeError):
        accepted = False
    return phase3 | ({borrower.lower()} if accepted else set())


def display(event):
    decimals = int(event['underlying_decimals'])
    whole, fraction = divmod(int(event['repayAmount']), 10**decimals)
    amount = str(whole) + ('.' + str(fraction).zfill(decimals) if decimals else '')
    return {'borrower_short': event['borrower'][:6] + '…' + event['borrower'][-4:],
            'market_symbol': event['repaid_market_symbol'],
            'market_label': market_label(event.get('repaid_market', ''), event['repaid_market_symbol']), 'repay_amount': amount,
            'block': event['blockNumber']}


def market_label(market, symbol):
    proof = load(ROOT / 'data/phase2/market_label_verification.json')
    if market.lower() == proof['market']:
        return proof['market_label']
    return symbol
