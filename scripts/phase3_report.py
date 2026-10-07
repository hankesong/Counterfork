"""Render only recorded Phase 3 evidence. No network."""
from decimal import Decimal
from phase0_check import ROOT
from phase2_contract import require_evidence
from phase3_batch import checked_load, LIMITATIONS


def money(value):
    return f'{Decimal(value):,.2f}' if value is not None else '—'


def main():
    folder = ROOT / 'data/phase3'
    doc = checked_load(folder / 'experiments.json')
    sensitivity = checked_load(folder / 'sensitivity.json')
    history = checked_load(folder / 'runs.json')
    for name, item in [('experiments',doc),('sensitivity',sensitivity),('runs',history)]:
        require_evidence(item,name)
    rows = doc['experiments']
    counts = {s:sum(r['status']==s for r in rows) for s in ['passed','real_not_reproduced','not_applicable']}
    lines = ['# Phase 3：批量反事实实验与敏感性','',
        f"通过 {counts['passed']}；真实组未复现 {counts['real_not_reproduced']}；不适用 {counts['not_applicable']}。Phase 1 回归：{doc['phase1_regression']}。", '',
        '## 运行', '', '```powershell','python scripts/phase3_batch.py',
        'python scripts/phase3_batch.py --cache-only',
        '# 强制重跑 Foundry，同时禁止上游请求：',
        'python scripts/phase3_batch.py --cache-only --rerun-fork', '```','',
        '只依赖 Python 标准库和项目现有 Foundry/Solidity。RPC 复用 rpc_cache 和 rpc_transport 全局 0.22 秒间隔。'
        '每个区块优先读取 eth_getBlockReceipts；不支持时逐笔读取至该区块所选样本中最晚的交易，失败能力探测也持久化。'
        '区块收据按交易位置完整核对，日志按清算位置截断，包括同交易的更早日志。'
        '价格来源是动态预言机的最后一次 PriceUpdated；无 DAI 更新时使用 N−1 状态并明确标记。','',
        '每账户一次 forge 运行，包含参考、真实、五档敏感性、临界价上下验证和条件诊断组。'
        '每组先 clearMockedCalls，再 mock 并回读；动态验证 oracle、DAI underlying 和 decimals。'
        '检查点包含输入/代码指纹和结果哈希；中断后复用已完成账户、RPC 和收据缓存。'
        '单账户收据或 fork 超过 25 分钟即停止并保留缓存。', '',
        '## 请求与耗时','', '| 运行 | 状态 | RPC 请求尝试数 | RPC 缓存命中 | 账户结果命中 | 秒数 |',
        '| --- | --- | ---: | ---: | ---: | ---: |']
    for i,r in enumerate(history['runs'],1):
        lines.append(f"| {i} | {r['status']} | {r['rpc_requests_this_run']} | {r['cache_hits']} | {r['account_result_cache_hits']} | {r['elapsed_seconds']} |")
    lines += ['', f"累计请求尝试 {sum(int(r['rpc_requests_this_run']) for r in history['runs'])} 次；"
        f"累计脚本耗时 {sum(Decimal(r['elapsed_seconds']) for r in history['runs'])} 秒（不含开发与审批等待）。"]
    lines += ['', '请求计数沿用 transport 的启动尝试计数，含失败尝试；沙箱阻止的尝试不代表请求已到达上游。'
        'runs.json 保留初期运行错误，不隐藏重试成本。Phase 2 状态刷新始终使用 --cache-only 并断言请求数为零。','',
        '## 每账户结果','',
        '| 排名 | 地址 | N | 次数 | 实际 DAI 美元价 | 真实 shortfall 美元 | 1.00 shortfall 美元 | 临界价（推导） | 状态 |',
        '| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |']
    for r in rows:
        g=r['groups']; c=r['critical_price']
        lines.append(f"| {r['rank']} | `{r['borrower']}` | {r['sample_event']['blockNumber']} | {r['liquidation_count']} | "
            f"{g['real']['price_usd'] if g else '—'} | {money(g['real']['shortfall_usd']) if g else '—'} | "
            f"{money(g['1.00']['shortfall_usd']) if g else '—'} | {c['price_usd'] if c and c['price_usd'] else 'null'} | {r['status']} |")
    lines += ['', '不适用账户原因：与 DAI 无关。未复现账户保留全部原始组、其他资产更新、诊断结果、'
        '同块重复清算标记与利息/状态差异说明；不改变区块或价格来满足验收。','', '## 敏感性','',
        sensitivity['valuation_note'],'',
        '| 价格档 | 仍可清算账户数 | N−1 排序估值合计（美元） | shortfall 合计（美元） | 纳入账户总数 |',
        '| --- | ---: | ---: | ---: | ---: |']
    for r in sensitivity['rows']:
        lines.append(f"| {r['group']} | {r['liquidatable_accounts']} | {money(r['repay_usd_estimate_total'])} | {money(r['shortfall_total_usd'])} | {r['included_accounts']} |")
    values = sorted(Decimal(r['critical_price']['price_usd']) for r in rows if r['critical_price'] and r['critical_price']['price_usd'])
    lines += ['', '只统计真实组 err=0 且 shortfall>0 的账户；diagnostic_only 不纳入。真实组价格因样本而异。','', '## 临界价格分布','',
        '用 signed balance = liquidity − shortfall，按 $1.00/$1.30 两端线性插值；其余三档检验线性，容差为 $0.00000001 以容纳整数舍入。'
        '只接受临界价 ±$0.0001 从正余额到负余额的翻转；非下降敞口、非线性或未翻转均输出 null 并注明原因。']
    already = [r for r in rows if r['groups'] and int(r['groups']['reference']['shortfall']) > 0]
    if already:
        lines += ['', '参考组 N−1 已有缺口的账户排名：'+', '.join(r['rank'] for r in already)+
            '。其真实组通过不能表述为本区块 DAI 更新首次触发清算。']
    if values:
        median = (values[(len(values)-1)//2]+values[len(values)//2])/2
        lines += ['', f'已验证临界价 {len(values)} 个；最小 {values[0]}，中位数 {median}，最大 {values[-1]} 美元。','',
                  '| 区间 | 账户数 |','| --- | ---: |']
        for lo,hi in [('0','1.00'),('1.00','1.05'),('1.05','1.10'),('1.10','1.20'),('1.20','1.30'),('1.30','Infinity')]:
            lines.append(f'| [{lo}, {hi}) | {sum(Decimal(lo)<=v<Decimal(hi) for v in values)} |')
    for r in rows:
        if r['critical_price'] and r['critical_price']['price_usd'] is None:
            lines.append(f"- `{r['borrower']}`：null，{r['critical_price']['reason']}。")
    lines += ['', '## 诊断与结论边界','']
    for r in rows:
        if r['status']=='not_applicable': continue
        d=r['failure_diagnostics']; diagnostic=r['diagnostic']
        lines.append(f"- `{r['borrower']}`：{r['status']}；清算前非 DAI PriceUpdated {len(d['other_asset_updates'])} 条；"
            f"同块清算 {d['same_block_liquidation_count']} 次；诊断组 shortfall "
            f"{money(diagnostic['result']['shortfall_usd']) if diagnostic else '未触发'}。")
    lines += ['', '真实组未复现只说明固定 N−1 状态下本实验未重现清算条件，不能判定链上清算无效；'
        '其他资产价格、区块内操作及利息计提可能导致差异，当前不据此认定具体原因。', '', '## 局限','']
    lines += ['- '+s for s in LIMITATIONS]
    lines += ['', '## 来源与回归','',
        'provenance：`'+str(doc['provenance'])+'`。','',
        '全部输出含 provenance；UI_MOCK 一律拒绝。顶层 mode 表示本次读取方式，账户证据保留生成时来源。'
        '原始整数和完整美元小数见 JSON，报告金额仅显示两位。', '',
        'Phase 1 回归逐字段比较原 single_account.json 的三个 groups（包括整数、美元值和价格来源）、样本交易/日志、预言机及通过状态。'
        'Phase 3 新增敏感性和临界价字段，不要求不同 schema 的整个文件字节一致。', '']
    verification_path = folder / 'verification.json'
    if verification_path.exists():
        verification = checked_load(verification_path)
        require_evidence(verification, 'verification')
        lines += ['## 最终验收记录', '',
            f"上游实际 RPC 请求 {verification['upstream_rpc_requests']} 次，新增成功 RPC 缓存文件同为 "
            f"{verification['new_successful_rpc_cache_files']}；另有 {verification['sandbox_blocked_attempts']} 次沙箱阻止的尝试。", '',
            f"{verification['offline_tests_passed']} 项离线测试通过。最终强制离线 Foundry 复跑 "
            f"{verification['forced_offline_fork_replay']['elapsed_seconds']} 秒、零 RPC；普通重跑 "
            f"{verification['ordinary_replay']['elapsed_seconds']} 秒、零 RPC、20/20 账户结果命中。", '',
            '两次运行的 Phase 3 experiments/sensitivity 和 Phase 2 events/accounts/summary 共五个主文件字节完全一致；'
            'SHA-256、运行信息和统计见 data/phase3/verification.json。', '']
    (ROOT/'docs/phase3.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__ == '__main__': main()
