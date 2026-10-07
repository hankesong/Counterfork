"""Audit LLM with mandatory, evidence-bound claims and deterministic rendering."""
from phase4_common import (ROOT, EXP, SENS, SUMMARY, HYP, RULES, Client, REF,
    check_all_text, dump, env_config, evidence, ref, render, resolve, sources)


def claim_specs(data):
    """Closed claims bind numeric evidence, status and scope before explanation."""
    stats = data[HYP]['evidence_summary']
    def h(path):
        return ref(HYP, '/evidence_summary/' + path)
    def s(i, key):
        return ref(SENS, f'/rows/{i}/{key}')
    specs = []
    def add(topic, claim, status, indices=(), extra=()):
        refs = list(dict.fromkeys([m.group() for m in REF.finditer(claim)] + list(extra)))
        accounts = [{'address': ref(EXP, f'/experiments/{i}/borrower'),
                     'block': ref(EXP, f'/experiments/{i}/sample_event/blockNumber')}
                    for i in indices]
        refs += [r for a in accounts for r in a.values() if r not in refs]
        specs.append({'topic': topic, 'claim': claim, 'status': status,
                      'evidence_refs': refs, 'accounts': accounts})
    def indices(key):
        return [int(i) for i in stats[key]['indices']]
    passed = indices('passed')
    add('low_prices', f"通过组共 {h('passed/count')} 个账户；DAI 价格为 {s(0, 'price_usd')} 和 {s(1, 'price_usd')} 美元时，"
        f"仍可清算账户分别为 {s(0, 'liquidatable_accounts')} 和 {s(1, 'liquidatable_accounts')}。这支持固定状态下的价格敏感性，不证明预言机是整个事件的原因。",
        'SUPPORTED', passed, [ref(EXP, f'/experiments/{i}/groups') for i in passed])
    add('critical_prices', f"已验证临界价格共 {h('critical/count')} 个，最小 {h('critical/minimum')}、中位数 {h('critical/median')}、"
        f"最大 {h('critical/maximum')} 美元；此分布包含真实组未复现账户，不能与仅纳入通过账户的敏感性表混为一谈。",
        'SUPPORTED', [i for i, r in enumerate(data[EXP]['experiments']) if r['critical_price'] and r['critical_price']['price_usd']],
        stats['critical']['evidence_refs'])
    add('preexisting_shortfalls', f"{h('preexisting/count')} 个账户在 N−1 已有缺口；把这些账户说成本区块 DAI 喂价首次触发清算，证据不支持。",
        'NOT_SUPPORTED', indices('preexisting'), [ref(EXP, f'/experiments/{i}/groups/reference') for i in indices('preexisting')])
    add('real_not_reproduced', f"真实组未复现 {h('not_reproduced/count')} 个账户。这只说明固定 N−1 状态的单变量实验未重现清算条件，不能认定链上清算无效。",
        'UNVERIFIED', indices('not_reproduced'), [ref(EXP, f'/experiments/{i}/groups/real') for i in indices('not_reproduced')])
    add('other_asset_diagnostic', f"其中 {h('diagnostic_reproduced/count')} 个账户在同时修改其他资产价格的诊断组中复现。该组改变多个变量，仅作诊断；H2 抵押品真实下跌仍未验证。",
        'DIAGNOSTIC_ONLY', indices('diagnostic_reproduced'), [ref(EXP, f'/experiments/{i}/diagnostic/result') for i in indices('diagnostic_reproduced')])
    unknown = indices('unexplained')
    add('unexplained', f"仍有 {h('unexplained/count')} 个账户未解释：" + '、'.join(ref(EXP, f'/experiments/{i}/borrower') for i in unknown)
        + '。诊断组也未重现清算条件，不能据此指定原因。', 'UNVERIFIED', unknown,
        [ref(EXP, f'/experiments/{i}/diagnostic/result') for i in unknown])
    for i in indices('not_applicable'):
        add('not_applicable', f"排名 {ref(EXP, f'/experiments/{i}/rank')} 的账户 {ref(EXP, f'/experiments/{i}/borrower')}："
            f"{ref(EXP, f'/experiments/{i}/reason')}，DAI 改价模板不适用。", 'UNVERIFIED', [i],
            [ref(EXP, f'/experiments/{i}/status')])
    add('valuation_scope', '敏感性表的估值合计是账户全天偿还额的 N−1 排序估值，不是在该价格下会被清算的金额，也不是损失。',
        'SUPPORTED', passed, [ref(SENS, '/valuation_note'), ref(EXP, '/valuation_note')])
    for i, row in enumerate(data[HYP]['hypotheses']):
        if not row['run_experiment']:
            add('unverified_' + row['id'], row['id'] + ' 未开展对应实验，保持未验证。', 'UNVERIFIED', (), [ref(HYP, f'/hypotheses/{i}')])
    return specs


def fixed_sections(data):
    limitations = [ref(EXP, f'/limitations/{i}') for i in range(len(data[EXP]['limitations']))]
    limitations += ['补实验回路未实现', '假设模型输入不含日内时间直方图和前二十账户明细；这些字段在事件摘要中缺失。',
                   '模型解释仅作辅助阅读；状态、引用和必需事实由确定性校验约束，仍需人工审核语义。']
    sensitivity = [{k: ref(SENS, f'/rows/{i}/{k}') for k in row} for i, row in enumerate(data[SENS]['rows'])]
    bins = [{k: ref(HYP, f'/evidence_summary/critical/bins/{i}/{k}') for k in row}
            for i, row in enumerate(data[HYP]['evidence_summary']['critical']['bins'])]
    return {'sensitivity_summary': {'rows': sensitivity, 'valuation_note': ref(SENS, '/valuation_note'), 'critical_distribution': bins},
        'assumptions_and_limitations': limitations,
        'unverified_hypotheses': [r['id'] for r in data[HYP]['hypotheses'] if not r['run_experiment']]}


def validate_report(value, data):
    check_all_text(value, data)
    if not isinstance(value, dict) or set(value) != {'conclusions', 'sensitivity_summary', 'uncertainty', 'assumptions_and_limitations', 'unverified_hypotheses'}:
        raise ValueError('invalid report schema')
    expected = claim_specs(data)
    rows = value['conclusions']
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('missing required conclusion')
    for row, spec in zip(rows, expected):
        evidence(row, data)
        if set(row) != set(spec) | {'explanation'}:
            raise ValueError('conclusion needs exact required fields plus explanation')
        for key, item in spec.items():
            if row[key] != item:
                raise ValueError('mandatory evidence-bound conclusion mismatch: ' + spec['topic'] + '/' + key)
        if not isinstance(row['explanation'], str) or not row['explanation'].strip():
            raise ValueError('explanation required')
    for key, item in fixed_sections(data).items():
        if value[key] != item:
            raise ValueError('mandatory section mismatch: ' + key)
    if not isinstance(value['uncertainty'], list) or not value['uncertainty']:
        raise ValueError('uncertainty must be a nonempty text list')
    for item in value['uncertainty']:
        if not isinstance(item, str):
            raise ValueError('uncertainty requires text')


def compact_evidence(value):
    """Keep original pointers, exclude raw logs from prompts."""
    if isinstance(value, list):
        return [compact_evidence(v) for v in value]
    if isinstance(value, dict):
        return {k: compact_evidence(v) for k, v in value.items()
                if k not in ('log', 'price_updates', 'other_asset_updates', 'prices')}
    return value


def run(client, data):
    prompt = RULES + '''
审核这些冻结证据。输出 required_sections 的全部字段，再加 conclusions 和 uncertainty。
conclusions 必须逐条原样保留 required_conclusions 中每条的 topic、claim、status、evidence_refs、accounts；
为每条增加 explanation：用简短中文解释证据的意义和边界。不得增加未经证实的事实。
uncertainty 是非空中文文本列表，讨论未重放交易、利息计提和未复现账户的原因不确定性。
assumptions_and_limitations 必须原样保留全部引用与文字，尤其补实验回路未实现。
别把多个变量的诊断组解释为 H2 被验证，也不能把 N−1 已有缺口说成本区块首次触发。
不要在解释中重复数量；必须使用数字时只能引用。不要将区块或价格写成中文数字绕过限制。'''
    value = client.ask(prompt, {'evidence_files': compact_evidence(data),
        'required_conclusions': claim_specs(data), 'required_sections': fixed_sections(data)},
        lambda v: validate_report(v, data))
    value.update({'schemaVersion': '1', 'model': client.config['LLM_MODEL'],
        'provenance': {'mode': 'FROZEN', 'source': 'LLM audit of allowlisted frozen results; deterministic references'}})
    return value


def markdown(report, data):
    lines = ['# 调查报告', '', '模型：' + report['model'], '', '## 结论', '']
    for row in report['conclusions']:
        lines += [f"- **{row['status']}** — {render(row['claim'], data)}", '  ' + render(row['explanation'], data),
                  '  证据：' + '、'.join('`' + r + '`' for r in row['evidence_refs'])]
        if row['accounts']:
            lines += ['  账户 / 清算块 N：' + '；'.join(render(a['address'], data) + ' / ' + render(a['block'], data) for a in row['accounts'])]
    lines += ['', '## 敏感性', '', render(report['sensitivity_summary']['valuation_note'], data), '',
              '| 价格档 | 可清算账户 | 纳入账户 | 全天排序估值合计 | 缺口合计 |', '| --- | ---: | ---: | ---: | ---: |']
    for row in report['sensitivity_summary']['rows']:
        lines.append('| ' + ' | '.join(render(row[k], data) for k in ('group', 'liquidatable_accounts', 'included_accounts', 'repay_usd_estimate_total', 'shortfall_total_usd')) + ' |')
    lines += ['', '### 临界价格分布', '', '| 下界（含） | 上界（不含） | 账户数 |', '| --- | --- | ---: |']
    for row in report['sensitivity_summary']['critical_distribution']:
        lines.append('| ' + ' | '.join(render(row[k], data) for k in ('lower', 'upper', 'count')) + ' |')
    for title, key in [('不确定性', 'uncertainty'), ('假设与局限', 'assumptions_and_limitations'), ('未验证假设', 'unverified_hypotheses')]:
        lines += ['', '## ' + title, ''] + ['- ' + render(s, data) for s in report[key]]
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    client = Client(env_config())
    data = sources(True)
    report = run(client, data)
    dump(ROOT / 'data/phase4/report.json', report)
    (ROOT / 'data/phase4/report.md').write_text(markdown(report, data), encoding='utf-8')
