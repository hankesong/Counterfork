"""Hypothesis LLM: structured Phase 2 features, closed experiment vocabulary."""
from decimal import Decimal
from phase4_common import (ROOT, EXP, SENS, SUMMARY, HYP, RULES, Client,
    check_all_text, dump, env_config, evidence, ref, resolve, sources)

CANDIDATES = {'H1': '预言机 DAI 价格异常', 'H2': '抵押品真实下跌',
              'H3': '协议参数变更', 'H4': '借款人自身操作'}
PRICES = ('1.00', '1.05', '1.10', '1.20', '1.30')


def validate_hypotheses(value, data):
    check_all_text(value, data)
    if not isinstance(value, dict) or set(value) != {'hypotheses'} or not isinstance(value['hypotheses'], list):
        raise ValueError('hypotheses object required')
    rows = value['hypotheses']
    if any(not isinstance(r, dict) for r in rows) or [r.get('id') for r in rows] != list(CANDIDATES):
        raise ValueError('must include exactly H1, H2, H3, H4 in order')
    for row in rows:
        if set(row) != {'id', 'reason', 'run_experiment', 'template', 'parameters', 'status', 'evidence_refs'}:
            raise ValueError('invalid hypothesis fields')
        evidence(row, data)
        if type(row['run_experiment']) is not bool:
            raise ValueError('run_experiment must be boolean')
        if not row['run_experiment']:
            if row['status'] != 'UNVERIFIED' or row['template'] is not None or row['parameters'] != {}:
                raise ValueError('untested hypothesis must be UNVERIFIED without experiment')
            continue
        if row['id'] != 'H1' or row['template'] != 'dai_price_override':
            raise ValueError('template not allowed for this hypothesis')
        if row['status'] != 'EXPERIMENT_COVERED' or set(row['parameters']) != {'prices'}:
            raise ValueError('invalid experiment fields')
        prices = row['parameters']['prices']
        if not isinstance(prices, list) or not prices:
            raise ValueError('nonempty price list required')
        selected = []
        for token in prices:
            price = resolve(token, data)
            if not isinstance(price, str) or price not in PRICES:
                raise ValueError('price outside template whitelist')
            selected.append(price)
            for account in data[EXP]['experiments']:
                if account['status'] == 'not_applicable':
                    continue
                group = account['groups'].get(price)
                if not group or Decimal(group['price_usd']) != Decimal(price) or group['err'] != '0':
                    raise ValueError('selected price not covered by actual Phase 3 experiments')
        if len(set(selected)) != len(selected):
            raise ValueError('duplicate selected price')


def derived_evidence(data):
    """Deterministic audit indices/counts. Never supplied as hypothesis features."""
    rows = data[EXP]['experiments']
    categories = {
        'passed': [i for i, r in enumerate(rows) if r['status'] == 'passed'],
        'not_reproduced': [i for i, r in enumerate(rows) if r['status'] == 'real_not_reproduced'],
        'not_applicable': [i for i, r in enumerate(rows) if r['status'] == 'not_applicable'],
        'preexisting': [i for i, r in enumerate(rows) if r['groups'] and int(r['groups']['reference']['shortfall']) > 0],
        'diagnostic_reproduced': [i for i, r in enumerate(rows) if r['status'] == 'real_not_reproduced'
            and r.get('diagnostic') and r['diagnostic']['result']['err'] == '0'
            and int(r['diagnostic']['result']['shortfall']) > 0],
    }
    categories['unexplained'] = [i for i in categories['not_reproduced'] if i not in categories['diagnostic_reproduced']]
    values = sorted(Decimal(r['critical_price']['price_usd']) for r in rows
                    if r['critical_price'] and r['critical_price']['price_usd'] is not None)
    result = {k: {'count': str(len(indices)), 'indices': [str(i) for i in indices],
                  'evidence_refs': [ref(EXP, f'/experiments/{i}') for i in indices]}
              for k, indices in categories.items()}
    if not values:
        raise ValueError('no verified critical prices')
    result['critical'] = {'count': str(len(values)), 'minimum': str(values[0]),
        'median': str((values[(len(values)-1)//2] + values[len(values)//2]) / 2), 'maximum': str(values[-1]),
        'bins': [{'lower': lo, 'upper': hi,
                  'count': str(sum(Decimal(lo) <= v < Decimal(hi) for v in values))}
                 for lo, hi in [('0', '1.00'), ('1.00', '1.05'), ('1.05', '1.10'),
                                ('1.10', '1.20'), ('1.20', '1.30'), ('1.30', 'Infinity')]],
        'evidence_refs': [ref(EXP, f'/experiments/{i}/critical_price') for i, r in enumerate(rows)
                          if r['critical_price'] and r['critical_price']['price_usd'] is not None]}
    return result


def run(client, data):
    summary = data[SUMMARY]
    fields = ('window', 'dai_related', 'dai_repaid', 'total', 'market_totals', 'valuation_note', 'scope')
    features = {k: summary[k] for k in fields}
    # No raw logs, account files or outcome data are given to the hypothesis model.
    prompt = RULES + '''
从固定候选中选择值得实验的假设，逐一解释理由。返回 {"hypotheses":[...]}，按候选顺序各列一次。
每项字段：id、reason、run_experiment 布尔、template、parameters、status、evidence_refs。
唯一模板 dai_price_override 只适用于 H1；参数 prices 是给定 price_choices 中完整引用的列表。
做实验时 status 为 EXPERIMENT_COVERED；这只表示已有对应实验，不表示原因得到验证。
未实验时 template=null、parameters={}、status=UNVERIFIED。其他假设没有可用模板。
只根据 summary 的结构化事件特征选择，不推测缺失的前排账户信息或日内分布。'''
    value = client.ask(prompt, {'candidates': CANDIDATES, 'summary_file': SUMMARY, 'summary': features,
        'unavailable_features': ['intraday_histogram', 'top_twenty_accounts'],
        'price_choices': [ref(SENS, f'/rows/{i}/price_usd') for i in range(5)],
        'price_choice_values': list(PRICES)}, lambda v: validate_hypotheses(v, data))
    value.update({'schemaVersion': '1', 'model': client.config['LLM_MODEL'],
        'provenance': {'mode': 'FROZEN', 'source': 'LLM selection of frozen structured Phase 2 summary'},
        'evidence_summary': derived_evidence(data),
        'feature_limitations': ['summary.json 不含日内时间直方图或前二十账户明细；未向假设模型提供这些数据。']})
    return value


if __name__ == '__main__':
    client = Client(env_config())
    dump(ROOT / HYP, run(client, sources()))
