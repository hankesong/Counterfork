# Phase 1：单账户反事实实验

验收通过：真实组 `err=0`、`shortfall>0`。在同一 N−1 账户状态下，DAI 从 $1.08 更新为清算前实际值 $1.095299，账户由剩余流动性 $119,323.20 变为缺口 $61,726.55；将 DAI 设为 $1.00 后缺口为零。

这支持“本样本在固定 N−1 状态下，DAI 价格更新足以使账户跨过清算阈值”。不据此声称整个事件由单一因素造成、存在操纵，或 $1.00 是当时市场真实价格。没有开始 Phase 2，没有 git 操作，没有链上写入或 BOT Chain 调用。

## 运行

在项目根目录，沿用 Phase 0 的 Python、Foundry、Solidity 和 `.env`：

```powershell
python scripts/phase1_single.py
```

脚本按样本收据核验、价格证据核验、Foundry 实验顺序执行。Python 仅标准库。已完成结果的代码和证据指纹都一致时，普通重跑直接复用结果；`result_cache_hit=true`、`rpc_requests_this_run=0`，不表示重新访问主网。

需要实际重跑 Foundry 时使用 `python scripts/phase1_single.py --rerun-fork`。本机也已实测该模式：相同结果，`rpc_requests_this_run=0`，历史读取命中 RPC/Foundry 缓存。逐次运行记录见 `data/phase1/runs.json`。

RPC 复用 `rpc_cache.rpc`，所有外部请求经过 `rpc_transport.rate_limit` 的跨进程文件锁，请求启动至少间隔 0.22 秒（任何一秒至多 5 次），包括本地代理转发的 Foundry 请求。没有扩展只读方法白名单。RPC URL 和凭证从 `.env` 读取，子进程输出统一脱敏。

## 样本与搜索范围

通过 `cast keccak "LiquidateBorrow(address,address,uint256,address,uint256)"` 核实主题：
`0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52`。

先复核当前节点与 `.env` 候选的 1/50 区块查询，再尝试公开报道，最后按 Phase 0 已验证的 blockHash 模式扫描：2020-11-26 08:00–10:00 UTC，区块 11332824–11333316，共 493 块、139 条 cDAI 清算事件。所选样本是这一完整窗口中 `repayAmount` 最大的一条，金额与报道约 4,600 万 DAI 的目标吻合；**没有扫描全天，不能证明全天最大，也未独立核实它与报道匿名大户的身份对应关系**。

主要限制及原文错误（详见 `data/phase1/discovery.json`）：

- 当前节点的 1/50 区块范围均返回 `eth_getLogs: RPC error code 27: Unknown state. First available state is 1`。
- 候选 1 返回 `eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL]`。
- 候选 2 的单块成功，50 块返回同一 code 27；候选 3 返回 `eth_getLogs: invalid or null response`。
- Invezz、The Block、Etherscan 交易列表返回 `HTTP Error 403: Forbidden`。Decrypt 可读，但未提供交易哈希；Google 页面为脚本验证页，Bing 结果无有效交易线索。未绕过验证。

| 字段 | 链上核实值 |
| --- | --- |
| 交易 | [0x53e09adb77d1e3ea593c933a85bd4472371e03da12e3fec853b5bc7fac50f3e4](https://etherscan.io/tx/0x53e09adb77d1e3ea593c933a85bd4472371e03da12e3fec853b5bc7fac50f3e4) |
| receipt.status | `0x1` |
| N / UTC | `11333037` / `2020-11-26 08:55:16` |
| N 哈希 | `0x51b1693ee9c8f7b274b822fdc15262bd550f782e3b6667cfe20ab560164275ab` |
| N−1 / UTC | `11333036` / `2020-11-26 08:55:00` |
| N−1 哈希 | `0xe3ca0f2dc00d72a4aaa55dc9f758c5b57b66ded83ac6c5fe7c7aee9a42a815e5` |
| transactionIndex / LiquidateBorrow logIndex（十进制） | `4` / `59` |
| liquidator | `0xe8468f05550563aa5bfc5fbcb344bf87aa2f6b84` |
| borrower | `0x909b443761bbd7fbb876ecde71a37e1433f6af6f` |
| repayAmount（原始整数） | `46142428595048940000000000` |
| 偿还 DAI 数量 | `46142428.59504894` |
| cTokenCollateral | `0x5d3a536e4d6dbd6114cc1ead35777bab948e3643`（cDAI） |
| seizeTokens（原始整数） | `239682512793648786` |

地址来自事件的五个非 indexed ABI word：liquidator、borrower、repayAmount、cTokenCollateral、seizeTokens。核对成功收据、cDAI 发出地址、主题、data、logIndex、区块号和哈希；N.parentHash 等于 N−1.hash。原始收据和区块保存在 `data/rpc/`，汇总在 `data/phase1/sample.json`。

## 清算实际使用的价格

预言机由 N−1 的 `comptroller.oracle()` 动态取得，并核对 N 时同地址：`0x922018674c12a7f0d394ebeef9b58f186cde13c1`。Foundry 再独立读取核对。cDAI.underlying() 为 Phase 0 已验证的 DAI 地址 `0x6b175474e89094c44da98b954eedeac495271d0f`，decimals 为 18。

[Etherscan 已验证源码（Exact Match）](https://etherscan.io/address/0x922018674c12a7f0d394ebeef9b58f186cde13c1#code) 确认合约为 `UniswapAnchoredView`。本地源码见 `data/phase1/oracle_source.sol`：

- `postPrices(bytes[],bytes[],string[])`：源码约第 1101 行。先写入 reporter 数据，再进行锚定检查。
- `PriceUpdated(string,uint256)`：第 1007 行声明；第 1131–1135 行写入 `prices` 后发出。`cast keccak` 主题为 `0x159e83f4712ba2552e68be9d848e49bf6dd35c24f19564ffd523b6549450a2f4`。
- `PriceGuarded`、`AnchorPriceUpdated`、`UniswapWindowUpdated` 以及底层 `Write` 不是最终有效报价写入，不能替代 `PriceUpdated`。
- 第 1087–1091 行：`getUnderlyingPrice = 10^30 * priceInternal(config) / config.baseUnit`。链上 DAI config.baseUnit = `10^18`，事件价格为 6 位小数，故 DAI 返回值 = 事件值 × `10^12`。

逐笔取出 transactionIndex 0–4 的全部 5 张收据；仅使用清算 logIndex 59 之前的日志。全部有效更新如下（同一区块全局 logIndex，十进制）：

| 交易 | logIndex | 资产 | 事件原始价格 | getUnderlyingPrice 尺度 | 美元值 |
| --- | --- | --- | --- | --- | --- |
| `0x7fe4cf62476a5c401ca0665c08a7bd939f15a14074d65b2984101a6c8f1ea4c6` | 4 | DAI | `1095299` | `1095299000000000000` | 1.095299 |
| `0x53e09adb77d1e3ea593c933a85bd4472371e03da12e3fec853b5bc7fac50f3e4` | 36 | DAI | `1095299` | `1095299000000000000` | 1.095299 |

最后一次更新位于清算交易自身。因此真实组来源使用清算交易 + logIndex 36。N−1 为 `1080000000000000000`（$1.08），不能把它误当作本次清算实际价格。区块 N 结束时 eth_call 返回 `1095299000000000000`，与清算前最后更新一致。

没有其他资产的有效 PriceUpdated；有锚定价格事件，已单独记录，但不表示其他资产最终报价改变。诊断组条件不成立，`fork_result.json` 中 diagnostic 为 null，未运行，未用于结论。

## Foundry 实际输出

`test/Phase1.t.sol` 使用原生 cheatcode 接口和环境变量，不依赖 forge-std。在 N−1 断言 chainid、block.number、timestamp、预言机、DAI 标的和精度。参考组不改价；真实组仅 mock cDAI；clearMockedCalls 后运行 $1 反事实组。每次 mock 都回读价格验证。输出所有数字均为字符串。

| 组 | DAI 原始价格 | 美元价格 | 来源 | err | liquidity 原始整数 | shortfall 原始整数 |
| --- | --- | --- | --- | --- | --- | --- |
| 参考 | `1080000000000000000` | 1.08 | N−1 预言机状态 | `0` | `119323202441326601289267` | `0` |
| 真实 | `1095299000000000000` | 1.095299 | 上述清算交易，logIndex 36 | `0` | `0` | `61726547573096117664531` |
| 反事实 | `1000000000000000000` | 1.00 | 明确的 $1 假设，vm.mockCall | `0` | `1066050439591063023036037` | `0` |

| 组 | liquidity 美元值 | shortfall 美元值 |
| --- | --- | --- |
| 参考 | 119323.202441326601289267 | 0 |
| 真实 | 0 | 61726.547573096117664531 |
| 反事实 | 1066050.439591063023036037 | 0 |

liquidity、shortfall 均除以 `10^18` 得美元值；err 是错误码，没有美元单位。Foundry：1 passed / 0 failed。链上事件、参考价格和 fork 结果交叉核对通过。没有调整价格或区块来满足验收。

## 缓存、文件与局限

- 新增：`scripts/phase1_single.py`（编排、核验、停止条件）、`scripts/phase1_discover.py`（查询限制与网页证据）、`scripts/phase1_scan.py`（有时限的窗口扫描）、`test/Phase1.t.sol`、本报告与 `data/phase1/` 证据文件。
- 修改：`foundry.toml` 增加 `./data/phase1` 写权限；`scripts/rpc_transport.py` 为本地只读代理增加可选持久缓存，默认行为不变。沿用既有限速，没有新增上游端点。
- 核心产物：`sample.json`、`price_evidence.json`、`oracle_verification.json`、`fork_result.json`、`single_account.json`、`forge_run.json`、`runs.json`；RPC 原始证据位于 `data/rpc/`。第三方网页快照移至已忽略的 `data/private/bing.html`、`data/private/search.html`、`data/private/decrypt.html`、`data/private/oracle_etherscan.html`，不提交；`data/phase1/oracle_source.sol` 和 `data/phase1/oracle_abi.json` 保留提交。脚本后续下载 HTML 也使用 `data/private/`。
- 第二次普通运行：结果缓存命中，RPC 请求数为 0。显式重跑 Foundry 也已做到 0 外部 RPC；这依赖本机已有历史数据缓存，不承诺清空缓存后仍为零。
- N−1 是近似状态，没有重放 N 中的早先交易或借款人操作；只还原了清算前预言机有效价格。
- `getAccountLiquidity` 不计提利息；`liquidateBorrow` 会先对借款和抵押市场计提利息。未量化本次计提造成的净缺口差异，不能把本实验缺口当作交易内部精确缺口。本次真实组通过，没有触发失败诊断或补实验。
- $1.00 是反事实假设；单账户结果不外推所有受影响账户，不证明操纵，不替代完整交易重放。
- 最大样本搜索仅覆盖 08:00–10:00 UTC。约 4,600 万 DAI 量级已链上证实，全天最大及报道身份对应仍未独立证明。
