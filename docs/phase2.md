# Phase 2：全天清算事件

**N−1 预言机价格估值，仅用于排序，不等于清算实际价格。**

## 运行与范围

```powershell
python scripts/phase2_events.py
```

仅使用 Python 标准库；cast 仅在本地计算 ABI calldata、selector 和 Keccak，不直接连接 RPC。所有 RPC 使用既有 rpc_cache、rpc_transport、只读白名单和跨进程全局 0.22 秒请求间隔。网页 HTML 存在已忽略的 data/private；核实后的源码、ABI 和来源记录在 data/phase2。

窗口：2020-11-26T00:00:00+00:00 至 2020-11-26T23:59:59+00:00；6533 块。

| 边界 | 区块 | Unix 时间戳 | UTC |
| --- | --- | --- | --- |
| preceding | 11330638 | 1606348798 | 2020-11-25T23:59:58+00:00 |
| first | 11330639 | 1606348824 | 2020-11-26T00:00:24+00:00 |
| last | 11337171 | 1606435178 | 2020-11-26T23:59:38+00:00 |
| following | 11337172 | 1606435218 | 2020-11-27T00:00:18+00:00 |

首、末边界由 Phase 0 同类的时间二分查找确定，且核对了窗口外紧邻区块。全部区块核对 number、时间及相邻 parentHash；每条事件核对地址、主题、区块号/哈希、交易在区块中的位置与去重。

## 市场核实与分布

Comptroller `0x3d9819210a31b4961b30ef54be2aed79b9c9cd3b` 的历史实现由 comptrollerImplementation() 动态读取：`0x7b5e3521a049c8ff88e6349f33044c6cc33c113c`。Etherscan Exact Match 源码及 ABI 确认 `getAllMarkets() public view returns (CToken[] memory)`；读取窗口首块状态得到以下市场。

| 市场展示名 | cToken 地址 | 标的 symbol | decimals | 事件数 | 偿还美元估值 |
| --- | --- | --- | ---: | ---: | ---: |
| cBAT | `0x6c8c6b02e7b2be14d4fa6022dfd6d75921d90e4e` | BAT | 18 | 1 | 2,094.44 |
| cDAI | `0x5d3a536e4d6dbd6114cc1ead35777bab948e3643` | DAI | 18 | 151 | 96,769,063.37 |
| cETH | `0x4ddc2d193948926d02f9b1fe9e1daa0718270ed5` | ETH | 18 | 3 | 2,139.65 |
| cREP | `0x158079ee67fce2f58472a96584a73c7ab9ac95c1` | REP | 18 | 0 | 0.00 |
| cUSDC | `0x39aa39c021dfbae8fac545936693ac917d5e7563` | USDC | 6 | 12 | 41,917.51 |
| cUSDT | `0xf650c3d88d12db855b8bf7d11be6c55a4e07dcc9` | USDT | 6 | 11 | 2,214,396.51 |
| cWBTC | `0xc11b1268c1a384e55c48c2391d8d480264a3a7f4` | WBTC | 8 | 2 | 33,362.45 |
| cZRX | `0xb3319f5d18bc0d84dd1b4825dcde5d5f7266d407` | ZRX | 18 | 0 | 0.00 |
| cSAI | `0xf5dce57282a584d2746faf1593d3121fcac444dc` | DAI | 18 | 0 | 0.00 |
| cUNI | `0x35a18000230da775cac24873d00ff85bccded550` | UNI | 18 | 0 | 0.00 |
| cCOMP | `0x70e36f6bf80a52b3b46b3af8e106cc0ed743e8e4` | COMP | 18 | 2 | 1,701.47 |

标的地址、原始 symbol 和 decimals 全部保存在 summary.json，ERC20 标的元数据逐个在窗口首块读取。两个历史市场的链上 symbol 都是 cDAI/DAI，不能按 symbol 合并；DAI 相关标记仅使用 Phase 0/1 已验证的 cDAI `0x5d3a536e4d6dbd6114cc1ead35777bab948e3643`。另一个同名市场 `0xf5dce57282a584d2746faf1593d3121fcac444dc` 的标的为 `0x89d24a6b4ccb1b6faa2625fe562bdd9a23260359`。

旧市场已核实为 cSAI：Etherscan 标的页面标题为 Sai Stablecoin v1.0 (SAI)，并注明 rebranded to SAI。证据见 data/phase2/market_label_verification.json，快照 data/private/sai_etherscan.html。原始 symbol 保留不变。

cETH 单独处理依据：Etherscan 已验证 CEther 源码继承 CToken，mint() 为 payable，接收 msg.value，ABI 没有 underlying()。原生 ETH 的金额单位为 wei（18 位）；输出 underlying=null。

事件签名 `LiquidateBorrow(address,address,uint256,address,uint256)` 从历史 cDAI 实现的已验证 ABI 取得，五个字段均为非 indexed。本地 cast keccak 核对主题为 `0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52`。

## 实际请求、耗时和续跑

初次独立准备运行：67 次 RPC、33 次缓存命中；该次尚未加入计时，耗时未记录，不估填。后续完整运行计时如下（各阶段明细见 runs.json）：

| 运行 | 状态 | RPC 请求数 | 缓存命中 | 秒数 |
| --- | --- | ---: | ---: | ---: |
| 1 | failed | 8813 | 1411 | 3288.197 |
| 2 | passed | 3668 | 10214 | 883.829 |
| 3 | passed | 0 | 13882 | 2.690 |
| 4 | passed | 0 | 13882 | 2.028 |
| 5 | passed | 0 | 13882 | 1.844 |
| 6 | failed | 0 | 13882 | 1.986 |
| 7 | failed | 0 | 8726 | 1.325 |
| 8 | failed | 0 | 9206 | 1.335 |
| 9 | passed | 0 | 13882 | 2.080 |
| 10 | passed | 0 | 13882 | 2.183 |
| 11 | passed | 0 | 13882 | 1.899 |
| 12 | passed | 0 | 13882 | 1.931 |
| 13 | passed | 0 | 13882 | 2.102 |
| 14 | passed | 0 | 13882 | 1.947 |

实际失败原文（已脱敏，保留记录；随后从缺失缓存续跑）：

- `NETWORK_ERROR: <urlopen error [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1082)>`
- `[Errno 2] No such file or directory: 'F:\\hankesong\\hanworkspace\\data\\phase2\\market_label_verification.json'`
- `[WinError 5] 拒绝访问。: 'F:\\hankesong\\hanworkspace\\data\\phase2\\scan_progress.tmp' -> 'F:\\hankesong\\hanworkspace\\data\\phase2\\scan_progress.json'`
- `[WinError 5] 拒绝访问。: 'F:\\hankesong\\hanworkspace\\data\\phase2\\scan_progress.tmp' -> 'F:\\hankesong\\hanworkspace\\data\\phase2\\scan_progress.json'`

含独立准备在内，已记录的 Phase 2 RPC 请求累计为 12548 次。

区块头和全市场日志各自按 RPC 参数缓存，逐块原子写入。中断后仅缺失请求访问网络。每块一次 eth_getLogs，blockHash 与全部 cToken 地址数组一起传入；不使用历史范围查询。每个阶段设置 29 分钟停止线，触发或失败后保留缓存并记录脱敏原文错误。

**Phase 1 缓存口径：**11332824–11333316 共 493 块的旧 cDAI 日志查询全部强制命中缓存，区块头也复用。但旧缓存的 address 是单个 cDAI，不能当作全部市场查询缓存；首轮另对这 493 块各发一次全市场数组查询，逐块核对其 cDAI 子集与旧缓存完全一致；原窗口有 139 条 cDAI、152 条全市场事件。成功抓取后的完整复跑（运行 3）直接命中全部缓存。这一必要差异已在执行前说明；没有把窄过滤结果冒充全市场缓存。

运行 1 因 SSL EOF 中断，运行 2 从缺失缓存续跑并完成；运行 3 重新执行全部读取、解码、校验、估值与汇总，`rpc_requests_this_run=0`，耗时 2.690 秒。events/accounts/summary 三份 JSON 的重跑前后 SHA-256 一致，见 replay_verification.json。截至本次计时运行合计 4,195.376 秒（含中断等待）；另有初始准备运行未记录耗时。

## 汇总与前 20 名

共 **182 条事件、154 个借款人**；偿还估值 **$99,064,675.42**。DAI 相关 153 条、$96,870,598.16；仅 DAI 被偿还 151 条、$96,769,063.37。

按借款人全部清算事件的偿还美元估值合计降序排列；清算次数按事件计，同一交易多条事件分别计数。

| 排名 | 借款人 | 清算次数 | 偿还美元估值合计 | DAI 相关 | 首次区块 |
| ---: | --- | ---: | ---: | --- | ---: |
| 1 | `0x909b443761bbd7fbb876ecde71a37e1433f6af6f` | 1 | 49,833,822.88 | 是 | 11333037 |
| 2 | `0xb1adceddb2941033a090dd166a462fe1c2029484` | 8 | 23,018,183.71 | 是 | 11333040 |
| 3 | `0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42` | 6 | 6,872,183.78 | 是 | 11333019 |
| 4 | `0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c` | 1 | 6,739,427.53 | 是 | 11333047 |
| 5 | `0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60` | 1 | 1,745,263.94 | 是 | 11333050 |
| 6 | `0x889abdd2bc0f3a884e607279ba132501698fbcd5` | 1 | 1,304,636.60 | 是 | 11333029 |
| 7 | `0xc9493738f07ddc43f1a004d4bb461fa42de23225` | 1 | 1,044,060.15 | 是 | 11333060 |
| 8 | `0x161fac24d54698755dab0fcd65e2c883928ca724` | 1 | 942,277.47 | 是 | 11333040 |
| 9 | `0x03324cfffabc10193de63186a374d7cfe932b162` | 1 | 921,968.70 | 是 | 11333019 |
| 10 | `0xdf63be2e473ba04c26b1609e51d08cf0d78e0913` | 1 | 870,097.62 | 是 | 11335996 |
| 11 | `0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc` | 1 | 769,374.18 | 是 | 11332948 |
| 12 | `0x141f59a0283303a6b882b4d6973e418f8d75f9b3` | 1 | 636,414.16 | 是 | 11333065 |
| 13 | `0xe24286adfc053f76888aa51d9a94f6c1519b4cba` | 1 | 363,906.74 | 是 | 11333053 |
| 14 | `0xdac0db00fd0953d8731f86c6908366388bfcc1f8` | 1 | 315,077.67 | 否 | 11331593 |
| 15 | `0x339dab47bdd20b4c05950c4306821896cfb1ff1a` | 1 | 199,022.46 | 是 | 11333025 |
| 16 | `0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba` | 2 | 186,230.95 | 是 | 11333040 |
| 17 | `0x5c7c6d069ba232718f37c27a9549b547c359e31c` | 1 | 172,357.75 | 是 | 11333067 |
| 18 | `0x57adad5729e839acd4019fc9e79c2685a42ed489` | 3 | 164,739.29 | 是 | 11331593 |
| 19 | `0x01adb5a14196d302004e3a1970a8bb3183dd2565` | 1 | 163,884.19 | 是 | 11333029 |
| 20 | `0xdb16bb1e9208c46fa0cd1d64fd290d017958f476` | 1 | 162,755.20 | 是 | 11333059 |

## 交叉核对

Phase 1 样本交易 0x53e09adb…f3e4、logIndex 59 恰好出现一次：解码字段、区块时间/哈希、交易位置一致，raw_log 与 data/phase1/sample.json 的 log 对象完全相同。旧文件的十进制 JSON 数字在 events.json 中按要求转为字符串。

全天 DAI 被偿还原始数量最大的一笔是 Phase 1 样本。最大值 `46142428595048940000000000`，交易 `0x53e09adb77d1e3ea593c933a85bd4472371e03da12e3fec853b5bc7fac50f3e4`，logIndex 59。这不核实媒体所述匿名账户的身份。

从完整排序事件列表随机不放回抽取 5 条，随机种子首次生成并持久化；重跑验证同一组收据。核对 status、交易/区块位置和完整日志字段。

| 交易 | logIndex | 区块 | 收据核对 |
| --- | ---: | ---: | --- |
| `0x4cdc4cba96b2c9f21e37b226becd4718adab4bbfa0bfaa34780e2e4873dca2fe` | 228 | 11333075 | 通过 |
| `0x6819285185d491baa9bf019a686c104baae7db01dc23c4f3cbd1b45e421f9a21` | 250 | 11333019 | 通过 |
| `0x397f3b5a862cbe69fa0d70568da9378aa01871f4642a2189d2ef92be177a8949` | 178 | 11333135 | 通过 |
| `0x6a5542a9e62c86fb2592c788f88265e23f319f582181b10cc43d33a112bd6e42` | 107 | 11333038 | 通过 |
| `0x663586abd0b7a1ebbf651afdff2f44cb42eb2ddbfec31cc672b3fc0896a0f8ec` | 17 | 11333135 | 通过 |

## 与公开报道比较

[Decrypt 报道](https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound) 正文确认过去 24 小时约 8,900 万美元。原 5,200 万基准无可核实出处，已移除；DAI 两项差额为 null。下表差额为本次估值减报道近似值，正值表示本次较高。

| 口径 | 本次估值 | 报道基准 | 差额 |
| --- | ---: | ---: | ---: |
| 全部 | 99,064,675.42 | 89,000,000 | 10,064,675.42 |
| DAI 相关（偿还或抵押） | 96,870,598.16 | 无可核实基准 | — |
| 仅 DAI 被偿还（补充口径） | 96,769,063.37 | 无可核实基准 | — |

可能原因：报道的滚动 24 小时与固定 UTC 自然日不一致；报道可能使用当时币价、交易内部价或被扣押抵押品价值，本次固定采用 N−1 预言机对偿还本金估值；DAI 相关的分类口径可能不同。本次仅统计 Compound v2 起始市场列表，不能外推到其他协议。该 Decrypt 报道本身也明确指向 Compound，因此“排除其他协议”只是跨报道比较时的范围限制，不能未经核实就断言它解释了本表差额。报道数字是近似值，缺少可复算的原始事件清单与精确估值时点；差额不能唯一归因。窗口和数据未为贴近报道而调整。

进一步检查：全天实际偿还 DAI 数量合计 86257791.813640208472326336，对应 N−1 价格范围 $1.001083–$1.238179。按本任务的 N−1 价格估值，比仅将每个 DAI 机械记作 $1 多 $10,511,271.56。DAI 数量与美元估值单位不同；还需要报道的精确窗口、资产分类和原始清单才能归因。该补充只是单位量对账，没有改变排序估值或进行反事实实验。

## 估值和局限

- 每个发生事件的 N−1 块动态读取 comptroller.oracle()，对唯一 (N−1, 偿还市场) 组合读取 getUnderlyingPrice。原始价格按 10^(36−标的精度) 缩放；偿还美元估值 = repayAmount × price_raw / 10^36。整数乘法累加后再格式化，JSON 保留全部精度，表格显示两位小数。
- 本次共涉及 106 个不同 N−1 区块和 112 个唯一价格组合；不是逐事件重复读取价格。
- N−1 预言机价格估值，仅用于排序，不等于清算实际价格。Phase 1 已证明同一区块内喂价可以改变实际价格；本阶段不重放交易或批量反事实实验。
- 市场列表取窗口首块，按要求固定；不能自动包含当天之后新列入的市场。
- 以历史只读 RPC 返回的区块、日志为证据，不自行验证区块共识或日志树包含证明；抽检 5 张收据不等于逐笔收据验证。
- 偿还额不等于扣押抵押品价值、清算人利润或借款人净损失；seizeTokens 是 cToken 原始数量。
- 数据并未证明市场操纵、媒体匿名人物身份或所有清算的共同原因。
- Phase 2 仅做事件核对；批量实验另见 docs/phase3.md。未 push、未访问 BOT Chain。

## 验证

`python -m unittest discover -s test -p test_phase2_events.py -v` 用于离线验证。覆盖真实样本解码、非法区块/主题/地址/交易位置及重复事件拒绝、跨精度估值、事件/市场/借款人合计相等、账户事件索引和数字字符串约束。

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

status 每次生成时读取 data/phase3/experiments.json 和 data/phase1/single_account.json。Phase 3 状态为 passed（同时校验真实组 err=0、shortfall>0）或 Phase 1 验收通过，两者满足其一即为 analyzed；其余为 pending。拒绝 UI_MOCK、非法 provenance 或自相矛盾的 passed 记录。仅离线读取验收文件，不执行新实验。

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

本次输出 provenance：`{'mode': 'FROZEN', 'source': 'Ethereum mainnet via cached eth_getLogs/eth_call', 'capturedAt': '2026-10-07T03:28:30Z'}`。
借款人状态：analyzed=14，pending=140。

追加要求的离线验收（contract_replay_verification.json）：

| 运行 | RPC 请求 | 缓存命中 | 秒数 |
| --- | ---: | ---: | ---: |
| first_run | 0 | 13882 | 2.028 |
| second_run | 0 | 13882 | 1.844 |

两次生成的三个主文件 SHA-256 相同。15 项离线测试通过；新增测试覆盖原字段不变、display 无舍入、验收文件缺失/失败时 pending、capturedAt 稳定，以及任一输入 UI_MOCK 拒绝。原契约前的 replay_verification.json 作为旧版历史验收保留。完整前 3 个账户和前 2 条事件（含来源）见 data/phase2/contract_samples.json。
