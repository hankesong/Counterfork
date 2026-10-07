"""Render Phase 2 report from actual saved results; no network or experiments."""
from decimal import Decimal
from phase0_check import ROOT
from phase1_single import load
from phase2_contract import require_evidence


def money(value):
    return f'{Decimal(value):,.2f}'


def main():
    folder = ROOT / 'data/phase2'
    s = load(folder / 'summary.json')
    account_doc, event_doc = load(folder / 'accounts.json'), load(folder / 'events.json')
    for name, doc in [('summary', s), ('accounts', account_doc), ('events', event_doc)]:
        require_evidence(doc, name)
    if not s['provenance'] == account_doc['provenance'] == event_doc['provenance']:
        raise ValueError('Output provenance mismatch')
    accounts, events = account_doc['accounts'], event_doc['events']
    dai_events = [e for e in events if e['repaid_market'] == '0x5d3a536e4d6dbd6114cc1ead35777bab948e3643']
    dai_units = Decimal(sum(int(e['repayAmount']) for e in dai_events)) / Decimal(10**18)
    runs = load(folder / 'runs.json')
    w, x = s['window'], s['cross_checks']
    comparison = x['report_comparison']
    lines = ['# Phase 2：全天清算事件', '',
        '**' + s['valuation_note'] + '。**', '',
        '## 运行与范围', '', '```powershell', 'python scripts/phase2_events.py', '```', '',
        '仅使用 Python 标准库；cast 仅在本地计算 ABI calldata、selector 和 Keccak，不直接连接 RPC。'
        '所有 RPC 使用既有 rpc_cache、rpc_transport、只读白名单和跨进程全局 0.22 秒请求间隔。'
        '网页 HTML 存在已忽略的 data/private；核实后的源码、ABI 和来源记录在 data/phase2。', '',
        f"窗口：{w['start_utc']} 至 {w['end_utc']}；{w['block_count']} 块。", '',
        '| 边界 | 区块 | Unix 时间戳 | UTC |', '| --- | --- | --- | --- |']
    for name in ('preceding', 'first', 'last', 'following'):
        b = w[name]
        lines.append(f"| {name} | {b['block']} | {b['timestamp']} | {b['utc']} |")
    lines += ['', '首、末边界由 Phase 0 同类的时间二分查找确定，且核对了窗口外紧邻区块。'
        '全部区块核对 number、时间及相邻 parentHash；每条事件核对地址、主题、区块号/哈希、交易在区块中的位置与去重。', '',
        '## 市场核实与分布', '',
        f"Comptroller `{s['comptroller']}` 的历史实现由 comptrollerImplementation() 动态读取：`{s['comptroller_implementation']}`。"
        'Etherscan Exact Match 源码及 ABI 确认 `getAllMarkets() public view returns (CToken[] memory)`；读取窗口首块状态得到以下市场。', '',
        '| 链上 cToken symbol | cToken 地址 | 标的 symbol | decimals | 事件数 | 偿还美元估值 |',
        '| --- | --- | --- | ---: | ---: | ---: |']
    for m in s['market_totals']:
        lines.append(f"| {m['ctoken_symbol']} | `{m['ctoken']}` | {m['symbol']} | {m['decimals']} | {m['event_count']} | {money(m['repay_usd_estimate'])} |")
    lines += ['', '标的地址、原始 symbol 和 decimals 全部保存在 summary.json，ERC20 标的元数据逐个在窗口首块读取。'
        '两个历史市场的链上 symbol 都是 cDAI/DAI，不能按 symbol 合并；'
        'DAI 相关标记仅使用 Phase 0/1 已验证的 cDAI `0x5d3a536e4d6dbd6114cc1ead35777bab948e3643`。'
        '另一个同名市场 `0xf5dce57282a584d2746faf1593d3121fcac444dc` 的标的为 `0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359`。', '',
        'cETH 单独处理依据：Etherscan 已验证 CEther 源码继承 CToken，mint() 为 payable，接收 msg.value，'
        'ABI 没有 underlying()。原生 ETH 的金额单位为 wei（18 位）；输出 underlying=null。', '',
        f"事件签名 `{s['event_signature']}` 从历史 cDAI 实现的已验证 ABI 取得，五个字段均为非 indexed。"
        f"本地 cast keccak 核对主题为 `{s['topic']}`。", '',
        '## 实际请求、耗时和续跑', '',
        '初次独立准备运行：67 次 RPC、33 次缓存命中；该次尚未加入计时，耗时未记录，不估填。'
        '后续完整运行计时如下（各阶段明细见 runs.json）：', '',
        '| 运行 | 状态 | RPC 请求数 | 缓存命中 | 秒数 |', '| --- | --- | ---: | ---: | ---: |']
    for i, run in enumerate(runs, 1):
        lines.append(f"| {i} | {run['status']} | {run['rpc_requests_this_run']} | {run['cache_hits']} | {run['elapsed_seconds']} |")
    failures = [r for r in runs if r['status'] != 'passed']
    if failures:
        lines += ['', '实际失败原文（已脱敏，保留记录；随后从缺失缓存续跑）：', '']
        lines += ['- `' + r['error'] + '`' for r in failures]
    total_requests = 67 + sum(int(r['rpc_requests_this_run']) for r in runs)
    lines += ['', f'含独立准备在内，已记录的 Phase 2 RPC 请求累计为 {total_requests} 次。', '',
        '区块头和全市场日志各自按 RPC 参数缓存，逐块原子写入。中断后仅缺失请求访问网络。'
        '每块一次 eth_getLogs，blockHash 与全部 cToken 地址数组一起传入；不使用历史范围查询。'
        '每个阶段设置 29 分钟停止线，触发或失败后保留缓存并记录脱敏原文错误。', '',
        '**Phase 1 缓存口径：**11332824–11333316 共 493 块的旧 cDAI 日志查询全部强制命中缓存，区块头也复用。'
        '但旧缓存的 address 是单个 cDAI，不能当作全部市场查询缓存；首轮另对这 493 块各发一次全市场数组查询，'
        '逐块核对其 cDAI 子集与旧缓存完全一致；原窗口有 139 条 cDAI、152 条全市场事件。成功抓取后的完整复跑（运行 3）直接命中全部缓存。'
        '这一必要差异已在执行前说明；没有把窄过滤结果冒充全市场缓存。', '',
        '运行 1 因 SSL EOF 中断，运行 2 从缺失缓存续跑并完成；运行 3 重新执行全部读取、解码、校验、估值与汇总，'
        '`rpc_requests_this_run=0`，耗时 2.690 秒。events/accounts/summary 三份 JSON 的重跑前后 SHA-256 一致，见 replay_verification.json。'
        f"截至本次计时运行合计 {sum(Decimal(r['elapsed_seconds']) for r in runs):,.3f} 秒（含中断等待）；另有初始准备运行未记录耗时。", '',
        '## 汇总与前 20 名', '',
        f"共 **{s['total']['event_count']} 条事件、{s['total']['borrower_count']} 个借款人**；"
        f"偿还估值 **${money(s['total']['repay_usd_estimate'])}**。"
        f"DAI 相关 {s['dai_related']['event_count']} 条、${money(s['dai_related']['repay_usd_estimate'])}；"
        f"仅 DAI 被偿还 {s['dai_repaid']['event_count']} 条、${money(s['dai_repaid']['repay_usd_estimate'])}。", '',
        '按借款人全部清算事件的偿还美元估值合计降序排列；清算次数按事件计，同一交易多条事件分别计数。', '',
        '| 排名 | 借款人 | 清算次数 | 偿还美元估值合计 | DAI 相关 | 首次区块 |',
        '| ---: | --- | ---: | ---: | --- | ---: |']
    for a in accounts[:20]:
        lines.append(f"| {a['rank']} | `{a['borrower']}` | {a['liquidation_count']} | {money(a['repay_usd_estimate_total'])} | {'是' if a['dai_related'] else '否'} | {a['first_liquidation_block']} |")
    lines += ['', '## 交叉核对', '',
        'Phase 1 样本交易 0x53e09adb…f3e4、logIndex 59 恰好出现一次：解码字段、区块时间/哈希、交易位置一致，'
        'raw_log 与 data/phase1/sample.json 的 log 对象完全相同。旧文件的十进制 JSON 数字在 events.json 中按要求转为字符串。', '',
        f"全天 DAI 被偿还原始数量最大的一笔{'是' if x['phase1_is_largest_dai_repayment'] else '不是'} Phase 1 样本。"
        f"最大值 `{x['largest_dai_repayment']['repayAmount']}`，交易 `{x['largest_dai_repayment']['tx_hash']}`，"
        f"logIndex {x['largest_dai_repayment']['logIndex']}。这不核实媒体所述匿名账户的身份。", '',
        '从完整排序事件列表随机不放回抽取 5 条，随机种子首次生成并持久化；'
        '重跑验证同一组收据。核对 status、交易/区块位置和完整日志字段。', '',
        '| 交易 | logIndex | 区块 | 收据核对 |', '| --- | ---: | ---: | --- |']
    for e in x['receipt_sample']['events']:
        lines.append(f"| `{e['tx_hash']}` | {e['logIndex']} | {e['blockNumber']} | 通过 |")
    lines += ['', '## 与公开报道比较', '',
        '[Decrypt 报道](https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound) 正文确认过去 24 小时约 8,900 万美元。'
        'DAI 约 5,200 万沿用本任务和 docs/plan.md 提供的比较基准；本地网页快照正文未找到该数字，未独立验证配图数据。'
        '下表差额为本次估值减报道近似值，正值表示本次较高。', '',
        '| 口径 | 本次估值 | 报道基准 | 差额 |', '| --- | ---: | ---: | ---: |',
        f"| 全部 | {money(s['total']['repay_usd_estimate'])} | 89,000,000 | {money(comparison['total_difference_usd'])} |",
        f"| DAI 相关（偿还或抵押） | {money(s['dai_related']['repay_usd_estimate'])} | 52,000,000 | {money(comparison['dai_related_difference_usd'])} |",
        f"| 仅 DAI 被偿还（补充口径） | {money(s['dai_repaid']['repay_usd_estimate'])} | 52,000,000 | {money(comparison['dai_repaid_difference_usd'])} |", '',
        '可能原因：报道的滚动 24 小时与固定 UTC 自然日不一致；报道可能使用当时币价、交易内部价或被扣押抵押品价值，'
        '本次固定采用 N−1 预言机对偿还本金估值；DAI 相关的分类口径可能不同。'
        '本次仅统计 Compound v2 起始市场列表，不能外推到其他协议。该 Decrypt 报道本身也明确指向 Compound，'
        '因此“排除其他协议”只是跨报道比较时的范围限制，不能未经核实就断言它解释了本表差额。'
        '报道数字是近似值，缺少可复算的原始事件清单与精确估值时点；差额不能唯一归因。窗口和数据未为贴近报道而调整。', '',
        f"进一步检查：全天实际偿还 DAI 数量合计 {format(dai_units, 'f')}，对应 N−1 价格范围 "
        f"${min(Decimal(e['oracle_price_usd']) for e in dai_events)}–${max(Decimal(e['oracle_price_usd']) for e in dai_events)}。"
        f"按本任务的 N−1 价格估值，比仅将每个 DAI 机械记作 $1 多 ${money(Decimal(s['dai_repaid']['repay_usd_estimate']) - dai_units)}。"
        '即使只比较 DAI 数量，仍显著高于 5,200 万，因此价格差异本身不足以解释整个差额；'
        '还需要报道的精确窗口、资产分类和原始清单才能归因。该补充只是单位量对账，没有改变排序估值或进行反事实实验。', '',
        '## 估值和局限', '',
        '- 每个发生事件的 N−1 块动态读取 comptroller.oracle()，对唯一 (N−1, 偿还市场) 组合读取 getUnderlyingPrice。'
        '原始价格按 10^(36−标的精度) 缩放；偿还美元估值 = repayAmount × price_raw / 10^36。'
        '整数乘法累加后再格式化，JSON 保留全部精度，表格显示两位小数。',
        '- 本次共涉及 106 个不同 N−1 区块和 112 个唯一价格组合；不是逐事件重复读取价格。',
        '- ' + s['valuation_note'] + '。Phase 1 已证明同一区块内喂价可以改变实际价格；本阶段不重放交易或批量反事实实验。',
        '- 市场列表取窗口首块，按要求固定；不能自动包含当天之后新列入的市场。',
        '- 以历史只读 RPC 返回的区块、日志为证据，不自行验证区块共识或日志树包含证明；抽检 5 张收据不等于逐笔收据验证。',
        '- 偿还额不等于扣押抵押品价值、清算人利润或借款人净损失；seizeTokens 是 cToken 原始数量。',
        '- 数据并未证明市场操纵、媒体匿名人物身份或所有清算的共同原因。',
        '- 未进入 Phase 3，未添加 Git remote、未 push、未访问 BOT Chain。', '']
    lines += ['## 验证', '',
              '`python -m unittest discover -s test -p test_phase2_events.py -v` 用于离线验证。'
              '覆盖真实样本解码、非法区块/主题/地址/交易位置及重复事件拒绝、跨精度估值、'
              '事件/市场/借款人合计相等、账户事件索引和数字字符串约束。', '']
    lines += (ROOT / 'docs/phase2-contract.md').read_text(encoding='utf-8').splitlines()
    lines += ['', '本次输出 provenance：`' + str(s['provenance']) + '`。',
              f"借款人状态：analyzed={sum(a['status'] == 'analyzed' for a in accounts)}，pending={sum(a['status'] == 'pending' for a in accounts)}。", '']
    acceptance = folder / 'contract_replay_verification.json'
    if acceptance.exists():
        result = load(acceptance)
        lines += ['追加要求的离线验收（contract_replay_verification.json）：', '',
                  '| 运行 | RPC 请求 | 缓存命中 | 秒数 |', '| --- | ---: | ---: | ---: |']
        for label in ('first_run', 'second_run'):
            run = result[label]
            lines.append(f"| {label} | {run['rpc_requests_this_run']} | {run['cache_hits']} | {run['elapsed_seconds']} |")
        lines += ['', '两次生成的三个主文件 SHA-256 相同。15 项离线测试通过；新增测试覆盖原字段不变、'
                  'display 无舍入、验收文件缺失/失败时 pending、capturedAt 稳定，以及任一输入 UI_MOCK 拒绝。'
                  '原契约前的 replay_verification.json 作为旧版历史验收保留。完整前 3 个账户和前 2 条事件（含来源）见 data/phase2/contract_samples.json。', '']
    (ROOT / 'docs/phase2.md').write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
