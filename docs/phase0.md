# Phase 0 环境检查

状态：已通过历史状态与 Foundry 分叉验收。尚未开始 Phase 1。

## 运行

在项目根目录执行（Python 仅使用标准库）：

```powershell
python scripts/phase0_check.py
```

本机 `.env` 已配置实际可用的免费 dRPC。2026-10-06 再次复核原指定 rpcfree：
Python urllib 明确使用 POST、`Content-Type: application/json` 和标准 JSON-RPC
请求体 `{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}`，
实际返回 HTTP 200 / `text/html`，标题为
`Free Ethereum RPC — No Signup, No API Key`，没有返回 JSON-RPC。
`cast chain-id --rpc-url [脱敏]` 原生直连也失败，退出码 1，错误为
`Error: deserialization error: expected value at line 1 column 1`，HTML 标题相同。
另一次 cast 经共享限速代理复核，上游同样返回 HTTP 200 / `text/html` / 相同标题。
只保存状态、类型、标题及命令退出信息，没有保存 HTML 正文。
该标题像介绍页，证据不足以认定为 CAPTCHA；没有尝试绕过任何验证。
由于连通性未通过，不对 rpcfree 继续执行历史 `oracle()` 调用。

**结论：继续使用 dRPC。** dRPC 的历史状态读取和 Foundry 分叉已通过，
本次还通过 `blockHash` 取得真实历史清算日志及成功收据；rpcfree 指定地址不能用作 JSON-RPC。
经用户授权尝试其他公开节点后切换；候选地址只保存在 `.env`。
不要把 `.env` 加入版本控制，参考 `.env.example` 配置其他机器。

首次运行会读取历史区块和合约，并运行 `test/Phase0.t.sol`。
完整结果缓存存在且代码指纹匹配时，再次运行不调用 RPC 或 Foundry。
日志中的 `result_cache_hit: true` 和 `rpc_requests_this_run: 0` 表示复用结果，
不表示重新验证了当前 RPC 的可用性。失败的连通性检查也缓存；
修改配置后会使用新端点对应的缓存，重试同一个失败端点可加 `--retry-rpc`。

## 实测结果

| 字段 | 值 |
| --- | --- |
| Chain ID | 1 |
| 分叉区块 | 11330639 |
| 区块时间 UTC | 2020-11-26 00:00:24 |
| 区块时间 北京时间 | 2020-11-26 08:00:24 |
| 区块哈希 | `0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3` |
| 历史预言机 | `0x922018674c12a7f0d394ebeef9b58f186cde13c1` |
| DAI 原始价格 | `1004040000000000000` |
| 标的 DAI 精度 | 18 |
| 美元价格（原始价格 / 10^18） | 1.00404 |
| Foundry | 1 passed / 0 failed / 0 skipped |

预言机地址由分叉状态下的 `comptroller.oracle()` 动态取得。
Foundry 还检查了 cDAI 的 `underlying()` 和 DAI 的 `decimals()`，
实际标的是 `0x6B175474E89094C44Da98b954EedeAC495271d0F`。
Python 用历史 `eth_call` 独立查询，并核对分叉输出的地址、价格、区块与时间。

## 地址核实与证据

- [Comptroller / Unitroller（Etherscan）](https://etherscan.io/address/0x3d9819210A31b4961b30EF54bE2aeD79B9c9Cd3B#code)
- [cDAI / CErc20Delegator（Etherscan）](https://etherscan.io/address/0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643#code)
- `data/phase0/address_verification.json`：页面身份及源码字符串核对记录。
  `oracle_getter: false` 仅表示简单字符串搜索未命中该页面 ABI；
  不表示该函数不存在。实际历史调用与分叉调用均已成功。
- `data/phase0/status.json`：正式验收结果。
- `data/phase0/fork_read.json`：Foundry 直接写出的链上读数。
- `data/phase0/forge_run.json`：实际测试日志。
- `data/rpc/*.json`：历史区块及 eth_call 的原始响应缓存。
- `data/private/rpc/*.json`：本地端点连通性诊断，不跟踪到版本控制。

## 范围与剩余问题

本次验收使用经过时间二分查找确认的 2020-11-26 UTC 首个区块。
它是环境检查区块，**不是已确认清算交易的 N−1**。
本阶段没有账户对照，也没有修改 DAI 价格。

### 历史日志诊断与抓取方案

完整逐请求参数和结果见 [RPC 测试表](phase0-rpc-tests.md) 及
`data/phase0/rpc_diagnostics.json`。区块参数均由 Python `hex()` 生成，
是无前导零的十六进制 quantity，范围计数包含两端。
dRPC 对 500 区块返回错误码 35，对 1/10/50/100 区块及去掉过滤条件返回
错误码 27（`Unknown state. First available state is 1`），而同一历史区块的
`blockHash` 查询成功。它能返回 2020 年的区块和非空清算日志，
因此不能把失败解释为我们超过 10000 区块或所有历史数据不可用。
可确认的是服务端历史范围查询与哈希查询行为不同；内部路由/索引原因未获服务商确认。
PublicNode 的范围查询要求个人 token，历史区块不可用；第三候选最小复核为 HTTP 525。
没有注册新服务或使用新的服务端点。

最终采用 dRPC：`eth_getBlockByNumber` 取哈希后，以 `eth_getLogs(blockHash)`
逐块获取。该模式最大跨度恰为 1，每个区块和日志段独立缓存。
`scripts/rpc_cache.py` 同时支持范围模式：从已验证最大跨度切分，遇范围过大类错误
自动减半，到单块仍失败则停止；分段清单保存成功布局，重跑无需重复失败请求。
`data/phase0/log_policy.json` 明确选择 `block_hash` / `max_span: 1`。
共享传输层用跨进程文件锁将外部请求启动间隔限制到至少 0.22 秒，覆盖所有 Python RPC
及经本地代理的 Foundry/cast 调用。原生 cast 独立诊断为串行单次读取，另设保守本地限速。
所有方法受只读白名单限制，未访问 BOT Chain。

### 已核实的单条样本（只做 Phase 0 验收）

- 时间：2020-11-26 09:00:15 UTC；N = 11333058；N−1 = 11333057。
- 交易：`0xb4ff3f106761e83691d12305fdb8b53da46c26928af50637a44fa43765c053ce`。
- 借款人：`0xd4c5226e2108c722bb86ff8327727410dc120b42`。
- `repayAmount`：`45054523940184558508084`（DAI 最小单位；18 位精度）。
- `cTokenCollateral`：`0x39aa39c021dfbae8fac545936693ac917d5e7563`。
- `cast keccak "LiquidateBorrow(address,address,uint256,address,uint256)"` 输出
  `0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52`，与日志主题一致。
- `eth_getTransactionReceipt`：`status=0x1`；核对交易哈希、区块号/哈希、
  cDAI 地址、主题、data 和 logIndex，确认事件确实在成功收据中。
- `data/phase0/sample.json` 保存解码字段与原始日志；区块、日志、收据原始响应均在 `data/rpc/`。
  优先检查 09:00 UTC 起的窗口；这是一个真实样本，不声称是当天首条或最大清算。

重跑 `python scripts/locate_phase0_sample.py` 实际输出
`{"network_requests": 0, "cache_hits": 52}`，仍重新核对缓存收据及日志。
重跑诊断输出 `diagnostic_cache_hit: true, network_requests: 0, rows: 44`。
减半重试、单块失败停止、非范围错误停止、哈希一致性、只读方法和共享限速的
6 项离线回归测试通过；Foundry 仍为 1 passed / 0 failed。
Foundry 日志另有 `WARN cache: non-matching block metadata`，已原样保留在
`data/phase0/forge_run.json`；此次历史区块号、时间、预言机和价格交叉核对均通过。

尚未开始账户实验、反事实改价或 Phase 1。

### 本地版本控制

已以 `main` 初始化 git；提交前执行 `git status --ignored`、`git ls-files`、
`git check-ignore` 和 `scripts/audit_git_secrets.py`。
`.env`、`.env.*`（除 `.env.example`）、`.tools/`、`out/`、`cache/`、
`data/private/`、`__pycache__/`、`.venv/` 均忽略。
RPC 缓存未检出 URL、敏感凭证字段或本机配置值，保留跟踪以支持离线复现。
没有添加 remote、push 或创建 GitHub 仓库。

## 本地工具与来源

- Python 3.14.6；Git 2.55.0.windows.3。
- Foundry 1.8.5，来自 `foundry-rs/foundry` 官方 GitHub Release。
  工作区路径 `.tools/foundry/`，下载 ZIP 的 SHA-256：
  `21f86b563d87404a68481f513bf3e419780ee536307b89c658215ae6f8f5aa45`。
- Solidity 0.8.30，来自 `ethereum/solc-bin` 官方发布。
  工作区路径 `.tools/solc.exe`，SHA-256：
  `ccbd3ed44d5fbd26fe039702d403421f1212d2e8752e3cbe3bfd074986911586`。
- 两项下载均在执行前核对官方发布元数据中的 SHA-256。
  `.tools/` 不纳入版本控制；当前 Foundry 配置适配本机 Windows。
- 使用原生 Foundry cheatcodes；本阶段没有引入 forge-std 或 Python 第三方库。
- 唯一方案文件为 `docs/plan.md`；根目录没有另一份方案文件，不保留或新建重复文件。
