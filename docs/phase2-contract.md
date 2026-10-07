## 前端数据契约

三个文件均为顶层 JSON 对象。`events.json` 为 `{provenance, events}`，`accounts.json` 为 `{provenance, accounts}`；原数组记录不删字段，分别移入同名数组。`summary.json` 在原对象上增加 provenance。前端只读这三个文件，不访问 RPC、不自行计算金额、精度换算或美元合计；直接显示 display 和已有估值字符串。筛选不改变原文件总计，DAI 总计直接读 summary.dai_related。

全部数值用字符串，布尔值仍为 boolean。下表 `string（整数）` 均为十进制，原始 RPC 的十六进制另行标明；地址均为 0x 开头的 20 字节地址，哈希为 32 字节。美元均指 N−1 预言机估值，不能标成实际成交额。`…` 是一个 Unicode 省略号；borrower_short 的前 6 字符包括 `0x`。

**来源与证据规则（所有文件共用）。** mode 仅允许 LIVE、FROZEN、UI_MOCK：LIVE 表示本次生成使用了实时 RPC 读取（也可复用部分缓存），FROZEN 表示全部来自缓存，UI_MOCK 只表示界面占位。Phase 2 只输出 LIVE/FROZEN。**UI_MOCK 数据不得作为证据；所有后续报告生成脚本遇到 UI_MOCK 必须报错。** 当前 phase2_report.py 已逐个检查三个文件，通过共享 require_evidence 拒绝 UI_MOCK、缺失/非法来源及来源不一致，写报告前即停止。后续生成器必须使用同一检查。

`capturedAt` 固定为 runs.json 中首次全天抓取运行的 started_utc（本次 `2026-10-07T03:28:30Z`），持久化在 provenance_origin.json，缓存重跑不刷新。初始独立源码/元数据准备未记录时间；它不是单条缓存创建时间、全部抓取完成时间，也不是链上事件时间。

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| provenance | object | — | 三个顶层对象共享的来源标记 |
| provenance.mode | string enum | — | LIVE / FROZEN / UI_MOCK；本次为 FROZEN |
| provenance.source | string | — | 固定 Ethereum mainnet via cached eth_getLogs/eth_call |
| provenance.capturedAt | string | UTC ISO 8601 | 首次全天抓取运行开始时间，重跑不刷新 |

**events.json。** `events` 类型为 Event[]，按 (blockNumber, logIndex) 数值升序。每个 Event 的字段：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| tx_hash | string | 交易哈希 | 事件所在交易 |
| blockNumber | string（整数） | 区块 | 事件区块 N |
| blockHash | string | 区块哈希 | 已与区块头核对 |
| blockTimestamp | string（整数） | Unix 秒 | 区块时间戳 |
| block_utc | string | UTC ISO 8601 | 同一时间戳的 UTC 表示 |
| transactionIndex | string（整数） | 从 0 开始的序号 | 交易在区块中的位置 |
| logIndex | string（整数） | 从 0 开始的序号 | 日志在区块中的位置；与 tx_hash 一起引用事件 |
| liquidator | string | 地址 | 清算人 |
| borrower | string | 地址 | 被清算借款人 |
| repayAmount | string（整数） | 标的最小单位 | 偿还原始整数，未缩放 |
| repaid_market | string | cToken 地址 | 发出事件的被偿还市场 |
| repaid_market_symbol | string | — | 链上 cToken symbol，不能作为唯一市场键 |
| underlying_symbol | string | — | 被偿还标的 symbol |
| underlying_decimals | string（整数） | 小数位数 | 被偿还标的精度 |
| cTokenCollateral | string | cToken 地址 | 抵押品市场 |
| collateral_market_symbol | string | — | 抵押品 cToken symbol |
| collateral_underlying_symbol | string | — | 抵押品标的 symbol |
| collateral_underlying_decimals | string（整数） | 小数位数 | 抵押品标的精度 |
| seizeTokens | string（整数） | 抵押 cToken 最小单位 | 扣押 cToken 数量；不是标的数量 |
| dai_related | boolean | — | repaid_market 或 cTokenCollateral 为已验证 cDAI 地址时为 true |
| raw_log | RawLog object | — | 不变的原始 RPC 日志，子字段见下表 |
| oracle_block | string（整数） | 区块 | 价格读取的 N−1 |
| oracle | string | 地址 | 该 N−1 块动态读取的预言机 |
| oracle_price_raw | string（整数） | USD × 10^(36−标的精度) | 原始 getUnderlyingPrice 返回值 |
| oracle_price_usd | string（十进制小数） | USD/标的单位 | 完整精度价格 |
| repay_usd_estimate | string（十进制小数） | USD | 本事件偿还排序估值 |
| valuation_note | string | — | N−1 预言机价格估值，仅用于排序，不等于清算实际价格 |
| display | object | — | 仅派生展示字段，原始字段不变 |
| display.borrower_short | string | — | borrower 前 6 字符…后 4 字符 |
| display.market_label | string | — | 前端一律显示此字段，旧市场为 cSAI，其余为链上 cToken symbol |
| display.market_symbol | string | — | repaid_market_symbol 的副本，如 cDAI |
| display.repay_amount | string（十进制小数） | 标的单位 | repayAmount / 10^underlying_decimals；整数分拆生成，保留全部小数位（含末尾零），不四舍五入 |
| display.block | string（整数） | 区块 | blockNumber 的副本 |

RawLog 的全部字段（均保持 RPC 原值）：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| address | string | 地址 | 发出日志的 cToken |
| topics | string[] | 32 字节主题哈希 | 本事件为单个签名主题 |
| data | string | 十六进制 ABI 字节 | 五个非 indexed 参数 |
| blockNumber | string（十六进制 quantity） | 区块 | 事件区块 |
| blockHash | string | 区块哈希 | 原始区块哈希 |
| blockTimestamp | string（十六进制 quantity，可选） | Unix 秒 | RPC 返回的区块时间；存在时已核对 |
| transactionHash | string | 交易哈希 | 所在交易 |
| transactionIndex | string（十六进制 quantity） | 从 0 开始的序号 | 交易在区块中的位置 |
| logIndex | string（十六进制 quantity） | 从 0 开始的序号 | 日志在区块中的位置 |
| removed | boolean | — | 是否被移除；输出事件均为 false |

**accounts.json。** `accounts` 类型为 Account[]，按 repay_usd_estimate_total 数值降序，相同金额按地址排序。每个 Account 的字段：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| borrower | string | 地址 | 借款人唯一键 |
| status | string enum | — | pending / analyzed；表示有无已验收实验，不表示债务是否清偿 |
| liquidation_count | string（整数） | 事件条数 | 清算次数；同交易多事件分别计数 |
| first_liquidation_block | string（整数） | 区块 | 首次清算区块 |
| last_liquidation_block | string（整数） | 区块 | 末次清算区块 |
| repay_usd_estimate_total | string（十进制小数） | USD | 该借款人全部事件估值之和 |
| dai_related | boolean | — | 任一所属事件 dai_related=true |
| valuation_note | string | — | 相同的 N−1 估值限制说明 |
| events | EventRef[] | — | 全部所属事件引用，按事件顺序 |
| events[].tx_hash | string | 交易哈希 | 引用交易 |
| events[].logIndex | string（整数） | 区块日志序号 | 引用日志 |
| rank | string（整数） | 从 1 开始的名次 | 全部借款人估值排名 |
| top20 | boolean | — | rank ≤ 20 |

status 每次生成时读取 data/phase1/single_account.json；只有文件存在、status=passed、真实组 err=0 且 shortfall>0、顶层 borrower 与 sample.borrower 一致时，该文件指向的借款人才为 analyzed，其余一律 pending。不存在或未通过验收时不凭地址授予 analyzed；不会执行新的实验。文件内容不合法时拒绝生成，防止静默误标。

**summary.json 顶层字段。** 下述复用类型的每个子字段在后续表中列出。

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| provenance | object | — | 共用来源标记，见首表 |
| window | Window object | — | 请求时间窗口及链上边界 |
| markets | Market[] | — | 窗口首块的全部市场 |
| comptroller | string | 地址 | Unitroller 地址 |
| comptroller_implementation | string | 地址 | 首块状态的历史实现 |
| oracle_at_start | string | 地址 | 首块动态读取的预言机 |
| event_signature | string | ABI 签名 | 已核实的 LiquidateBorrow 签名 |
| topic | string | 32 字节哈希 | 事件主题 |
| getAllMarkets_signature | string | ABI 签名 | 已核实的市场列表函数签名 |
| valuation_note | string | — | N−1 排序估值限制 |
| valuation_formula | string | — | repayAmount * oracle_price_raw / 10^36 |
| market_totals | (Market + Totals)[] | — | 每个被偿还市场的元数据与合计，包括零事件市场 |
| dai_related | Totals object | — | 任一侧为 cDAI 的事件合计；这里不是 boolean |
| dai_repaid | Totals object | — | 仅被偿还市场为 cDAI 的合计 |
| total | Totals object | — | 全部事件合计 |
| cross_checks | CrossChecks object | — | 样本、收据、媒体基准核对 |
| scope | string | — | 协议、市场列表时点与 DAI 定义 |

Window / BlockBoundary：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| start_utc | string | UTC ISO 8601 | 窗口起始时刻（包含） |
| end_utc | string | UTC ISO 8601 | 窗口结束时刻（包含） |
| block_count | string（整数） | 块 | 窗口区块总数 |
| first | BlockBoundary object | — | 首块 |
| last | BlockBoundary object | — | 末块 |
| preceding | BlockBoundary object | — | 首块之前的紧邻块 |
| following | BlockBoundary object | — | 末块之后的紧邻块 |
| 每个 BlockBoundary.block | string（整数） | 区块 | 区块号 |
| 每个 BlockBoundary.timestamp | string（整数） | Unix 秒 | 区块时间 |
| 每个 BlockBoundary.utc | string | UTC ISO 8601 | 区块 UTC 时间 |
| 每个 BlockBoundary.hash | string | 区块哈希 | 边界哈希 |

Market（用于 markets[] 与 market_totals[]）：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| ctoken | string | 地址 | 市场唯一键 |
| market_label | string | — | 前端市场展示名；不用原始 symbol 展示 |
| ctoken_symbol | string | — | 链上原始 cToken symbol |
| ctoken_decimals | string（整数） | 小数位数 | cToken 精度 |
| underlying | string / null | 地址 | ERC20 标的；原生 ETH 为 null |
| symbol | string | — | 标的原始 symbol；原生资产为 ETH |
| decimals | string（整数） | 小数位数 | 标的精度；ETH 为 18 |
| basis | string | — | 地址、元数据和 cETH 特殊处理依据 |

Totals（用于 market_totals[]、dai_related、dai_repaid、total）：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| event_count | string（整数） | 条 | 此集合的事件数 |
| borrower_count | string（整数） | 人/地址 | 此集合去重借款人数；不同市场不能直接相加 |
| repay_usd_estimate | string（十进制小数） | USD | 此集合的偿还估值合计 |

CrossChecks 及其嵌套字段：

| 字段 | 类型 | 单位 | 含义 |
| --- | --- | --- | --- |
| phase1_sample_fields_match | boolean | — | Phase 1 解码字段匹配 |
| phase1_raw_log_exact_match | boolean | — | 原始日志逐字段完全一致 |
| phase1_is_largest_dai_repayment | boolean | — | 样本是否为全天最大 DAI 偿还原始数量 |
| largest_dai_repayment | object | — | 全天最大 DAI 偿还事件 |
| largest_dai_repayment.tx_hash | string | 交易哈希 | 最大事件交易 |
| largest_dai_repayment.logIndex | string（整数） | 区块日志序号 | 最大事件日志位置 |
| largest_dai_repayment.blockNumber | string（整数） | 区块 | 最大事件区块 |
| largest_dai_repayment.repayAmount | string（整数） | DAI 最小单位 | 最大偿还原始数量 |
| largest_dai_repayment.repay_usd_estimate | string（十进制小数） | USD | 最大事件的排序估值 |
| receipt_sample | object | — | 随机收据抽样记录 |
| receipt_sample.seed | string（整数） | — | 持久化随机种子 |
| receipt_sample.method | string | — | 抽样方法说明 |
| receipt_sample.event_set_sha256 | string | SHA-256 十六进制 | 排序事件引用集合的指纹 |
| receipt_sample.events | object[] | — | 抽样的 5 条事件 |
| receipt_sample.events[].tx_hash | string | 交易哈希 | 抽样交易 |
| receipt_sample.events[].logIndex | string（整数） | 区块日志序号 | 抽样日志位置 |
| receipt_sample.events[].blockNumber | string（整数） | 区块 | 抽样事件区块 |
| receipt_sample.events[].verified | boolean | — | 收据核对是否通过 |
| report_comparison | object | — | 与公开报道基准的差额 |
| report_comparison.public_report_total_usd | string（十进制数） | USD | 报道全部清算近似基准 |
| report_comparison.public_report_dai_related_usd | null | — | 无可核实 DAI 报道基准，已移除 |
| report_comparison.total_difference_usd | string（十进制小数） | USD | 本次全部估值减基准，可为负 |
| report_comparison.dai_related_difference_usd | null | — | 无可核实 DAI 报道基准，已移除 |
| report_comparison.dai_repaid_difference_usd | null | — | 无可核实 DAI 报道基准，已移除 |
| report_comparison.dai_benchmark_note | string | — | 移除无出处基准的说明 |
| report_comparison.source | string | HTTPS URL | 媒体公开来源，不是 RPC URL |

离线重新生成及验收命令：`python scripts/phase2_events.py --cache-only`。此选项在缓存缺失时直接报错，禁止访问 RPC 或网页；不改变任何请求参数、抓取顺序或限速方式。重复执行后 rpc_requests_this_run 应为 "0"，provenance.mode 为 FROZEN，capturedAt 不变。

## 市场范围说明

抓取覆盖窗口起始时 comptroller.getAllMarkets() 返回的全部 Compound v2 市场（本次 11 个），并非只抓取 DAI。沿用固定起始市场列表的范围限制：不能据此声称涵盖当天之后新列入的市场。

事件通过 dai_related 区分是否与 DAI 相关；前端如果只展示 DAI，就按 `events.filter(event => event.dai_related === true)` 过滤。定义同时检查被偿还市场与抵押品市场的 cToken 地址，不能只看 symbol 或仅过滤 underlying_symbol=DAI。

这样既能分别核对报道的全部总额和 DAI 相关额，也能包含抵押品为 cDAI 的清算，因为其抵押品估值同样受 DAI 价格影响。该标记表示资产关联，不证明 DAI 价格导致了每次清算。两个历史市场的链上 symbol 同为 cDAI，仍按已验证地址区分。
