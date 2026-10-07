"""Deterministic structured features; no model/network and no upstream writes."""
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from canonical import canonical_hash, load
from phase4_common import ROOT, EXP, SUMMARY, FEATURES, CONSTANTS, dump, reject_mock

EVENTS = 'data/phase2/events.json'
ACCOUNTS = 'data/phase2/accounts.json'


def make_features(events, accounts, experiments, summary):
    for value in (events, accounts, experiments, summary):
        reject_mock(value)
        if value.get('provenance', {}).get('mode') not in ('FROZEN', 'LIVE'):
            raise ValueError('features require real evidence provenance')
    with localcontext() as context:
        context.prec = 100
        date = datetime.fromisoformat(summary['window']['start_utc']).astimezone(timezone.utc).date()
        hours = [{'hour_utc': f'{date.isoformat()}T{h:02d}:00:00Z', 'event_count': '0',
                  'repay_usd_estimate_total': '0'} for h in range(24)]
        by_borrower = {}
        for event in events['events']:
            stamp = datetime.fromtimestamp(int(event['blockTimestamp']), timezone.utc)
            if stamp.date() != date:
                raise ValueError('event outside expected UTC day')
            row = hours[stamp.hour]
            row['event_count'] = str(int(row['event_count']) + 1)
            row['repay_usd_estimate_total'] = format(Decimal(row['repay_usd_estimate_total']) + Decimal(event['repay_usd_estimate']), 'f')
            by_borrower.setdefault(event['borrower'], []).append(event)
        ranked = sorted(accounts['accounts'], key=lambda a: (-Decimal(a['repay_usd_estimate_total']), a['borrower']))[:20]
        top = []
        for index, account in enumerate(ranked):
            selected = by_borrower[account['borrower']]
            total = sum((Decimal(e['repay_usd_estimate']) for e in selected), Decimal(0))
            first_block = min(int(e['blockNumber']) for e in selected)
            if (int(account['liquidation_count']) != len(selected)
                    or total != Decimal(account['repay_usd_estimate_total'])
                    or first_block != int(account['first_liquidation_block'])
                    or account['dai_related'] != any(e['dai_related'] for e in selected)):
                raise ValueError('account summary does not match events')
            top.append({'rank': str(index + 1), **{k: account[k] for k in
                ('borrower', 'liquidation_count', 'repay_usd_estimate_total', 'dai_related', 'first_liquidation_block')}})
        total_value = sum((Decimal(h['repay_usd_estimate_total']) for h in hours), Decimal(0))
        if total_value != Decimal(summary['total']['repay_usd_estimate']) or len(events['events']) != int(summary['total']['event_count']):
            raise ValueError('hourly features disagree with Phase 2 total')
    changed = []
    for index, account in enumerate(experiments['experiments']):
        diagnostic = account.get('diagnostic')
        if not diagnostic:
            continue
        changes = [p for p in diagnostic['prices'] if p['symbol'] != 'DAI' and p['changed_from_reference']]
        if changes:
            changed.append({'borrower': account['borrower'], 'experiment_index': str(index),
                            'symbols': sorted({p['symbol'] for p in changes})})
    return {'schemaVersion': '1', 'hourly_utc': hours, 'top_accounts': top,
        'diagnostic_other_asset_price_changes': {'account_count': str(len(changed)), 'accounts': changed,
            'definition': '诊断组存在且 prices 中至少一项非 DAI 资产的 changed_from_reference 为真；只计账户，不作归因结论。'},
        'valuation_note': summary['valuation_note'],
        'provenance': {'mode': 'FROZEN', 'source': 'Deterministic aggregation of frozen Phase 2 events/accounts and Phase 3 diagnostic price records',
            'inputHashes': {EVENTS: canonical_hash(events), ACCOUNTS: canonical_hash(accounts),
                           EXP: canonical_hash(experiments), SUMMARY: canonical_hash(summary)}}}


def make_constants(experiments):
    """Derive the USD epsilon from recorded raw epsilon and recorded price scale."""
    reject_mock(experiments)
    epsilons = set()
    evidence = []
    with localcontext() as context:
        context.prec = 100
        for index, row in enumerate(experiments['experiments']):
            critical = row['critical_price']
            if not critical:
                continue
            group = row['groups']['1.00']
            scale = Decimal(group['dai_price_raw']) / Decimal(group['price_usd'])
            epsilons.add(format(Decimal(critical['epsilon_raw']) / scale, 'f'))
            evidence.append({'epsilon_raw': f'{EXP}#/experiments/{index}/critical_price/epsilon_raw',
                             'price_scale_group': f'{EXP}#/experiments/{index}/groups/1.00'})
    if len(epsilons) != 1:
        raise ValueError('critical-price epsilon is missing or inconsistent')
    return {'schemaVersion': '1', 'critical_price_epsilon_usd': epsilons.pop(),
        'derivation': 'epsilon_raw / (groups["1.00"].dai_price_raw / groups["1.00"].price_usd)',
        'provenance': {'mode': 'FROZEN', 'source': 'Unit conversion of recorded Phase 3 critical-price epsilon, no invented tolerance',
                       'experimentsHash': canonical_hash(experiments), 'evidence': evidence}}


def generate():
    events, accounts, experiments, summary = [load(ROOT / p) for p in (EVENTS, ACCOUNTS, EXP, SUMMARY)]
    return {FEATURES: make_features(events, accounts, experiments, summary), CONSTANTS: make_constants(experiments)}


def write_or_verify(existing=False):
    data = generate()
    for path, value in data.items():
        if existing:
            if load(ROOT / path) != value:
                raise ValueError('deterministic input differs: ' + path)
        else:
            dump(ROOT / path, value)
    return data


if __name__ == '__main__':
    write_or_verify()
