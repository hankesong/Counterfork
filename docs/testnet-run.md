# BOT Chain 测试网正式登记与隔离复现

> 以下为版本 1 的历史登记与复现记录。2026-10-07 的 v2 修正规则、producerCommits、指纹根因、Infura 预检和续跑命令以 `docs/phase4.md` 的「v2：来源追溯与追加发布」为准。RPC 现明确不属于上下文；不要求复现者使用与发布者相同的 URL。旧 script_commit 不再用于代替各阶段 producer commit。版本 1 的清单和链上登记保留不变。

2026-10-07（Asia/Tokyo）。**测试网正式演示，不计入比赛有效部署（比赛只认主网）**。本任务只向链 968 广播。主网 677 未广播，代码遇到 `--network mainnet` 立即退出。

## 正式合约与调查登记

- 合约：[0x00c51bb88ffd088501bf11177592528a6e8d43e4](https://scan.bohr.life/address/0x00c51bb88ffd088501bf11177592528a6e8d43e4)
- 部署者：`0xea68b4bFdEd757281911520b03374B9E7D70043a`，与彩排相同；新合约地址与旧彩排地址不同。
- 使用原 `src/InvestigationRegistry.sol`；Solidity 0.8.30+commit.73712a01、Paris、optimizer=true、runs=200。源码 SHA-256：`4e81070285b116efa706ff9566d52af5b6a0c916d465c1dc2f93233c436aa509`。链上 runtime bytecode 与本次编译结果完全相同。
- 旧彩排记录 `deployments/botchain-testnet.json` 保留不动。

| 用途 | 交易 | 区块 | 核验 |
| --- | --- | ---: | --- |
| 部署正式测试网合约 | [0xc4ed2a3094124839a2cada730f9660a2c2eb218ebb96ee5f2e0904938c0f90c3](https://scan.bohr.life/tx/0xc4ed2a3094124839a2cada730f9660a2c2eb218ebb96ee5f2e0904938c0f90c3) | 26007929 | receipt=1，runtime bytecode 一致 |
| submitInvestigation，版本 1 | [0x2155c9ca66d7f8282ba30e1316bc9a308bbf9dddfbc2180643d7554f37970965](https://scan.bohr.life/tx/0x2155c9ca66d7f8282ba30e1316bc9a308bbf9dddfbc2180643d7554f37970965) | 26007955 | receipt=1，完整记录 ABI 与事件一致 |

参数：

```json
{
  "caseId": "0x51aec3f6bc0c3ac98b0c63e7e15252ce548cfeeb15f780e4c744b6fefcbba2ef",
  "targetChainId": 1,
  "fromBlock": 11330639,
  "toBlock": 11337171,
  "manifestHash": "0xabd8759d0775d5954ee0c1ab9a5584f79d81e70f69f88ccd110db6779da1ada5",
  "manifestURI": "https://raw.githubusercontent.com/hankesong/Counterfork/465429b4360dd50fb6d295d62cf5caddae23c82b/data/phase4/manifest.json",
  "contract": "0x00c51bb88ffd088501bf11177592528a6e8d43e4",
  "chain_id": 968
}
```

`targetChainId=1` 表示调查对象 Ethereum。交易链始终为 968。caseId 经 `cast keccak` 计算；清单按 keccak256-jcs 完整规范化哈希，与 `docs/phase4.md` 一致。`git ls-remote origin` 实测 `refs/heads/main=465429b4360dd50fb6d295d62cf5caddae23c82b`，`git branch -r --contains` 包含 `origin/main`；实际下载上述 raw URL 后再次核验哈希一致。

发送前打印并保存全部参数。发送后比较 `getInvestigation` 的 author、targetChainId、fromBlock、toBlock、manifestHash、manifestURI、timestamp=1791365450、blockNumber=26007955 的完整 ABI 编码，确认 latestVersion=1；核对事件 emitter、topic0、indexed caseId 与 version/author/manifestHash。详见 `deployments/botchain-testnet-registrations.json` 与 `deployments/botchain-testnet-submit-parameters.json`。

## 命令与密钥选择

```powershell
python scripts/register.py check --network testnet
python scripts/register.py deploy --network testnet
python scripts/register.py submit --network testnet
python scripts/reproduce.py --network testnet --case compound-2020-11-26-dai --level quick --attest
# 可选；不加 --attest，避免同地址对同版本重复登记
python scripts/reproduce.py --network testnet --case compound-2020-11-26-dai --version 1 --level full
```

已登记过的部署、提交和同地址复现会被拒绝重复发送；应先查看日志与 receipt，不能盲目重跑广播。已有同名复现报告时也会拒绝覆盖，需先保留旧报告。默认 version 为链上 latestVersion，默认 level 为 full。

BOT 配置仅选择性解析 BOT_TESTNET_RPC_URL、BOT_TESTNET_CHAIN_ID、BOT_TESTNET_EXPLORER_URL、BOT_PRIVATE_KEY；缺少测试网 URL/链 ID/浏览器时分别使用 https://rpc.bohr.life、968、https://scan.bohr.life。每一次 `cast send` 前均独立执行 `cast chain-id`，结果必须为 968。Foundry 登记命令在不含 `.env` 的临时目录执行，只传白名单环境，避免自动载入仓库其他链配置。

复现读取 ETH_RPC_URL 仅用于以太坊历史状态；只读 RPC 白名单不含交易发送方法。复现者优先用 REPRODUCER_PRIVATE_KEY，否则用 BOT_PRIVATE_KEY。实际复现地址与发布者相同：**与发布者为同一地址，属于自我复现，仅作流程演示，不代表独立复现**。即使使用不同地址也不能据此证明不同主体。

## 隔离方式与范围

清单来自链上 URI，先校验 manifestHash、schema、结果投影定义、case 与区块范围，然后在临时 git worktree 检出 `1534471884aab536a8efaeabd088f8e6806e640c`。使用 `core.autocrlf=false` 保持 Git blob 原字节；不修改旧 commit 源码。

执行前删除临时目录的 data/rpc、data/private、data/phase3、cache、out，以及 data/phase2 中的结果 JSON；仅保留 Phase 2 静态合约源码、ABI 和验证输入。新 RPC 缓存、代理持久缓存和 Foundry 缓存全部为空。

quick 的样本选择与全天偿还估值权重来自固定 commit 的 Phase 2 输入，放在 worktree 外的临时 inputs 目录；它不重扫全天事件、不重新计算全天排名与权重。每个样本通过新请求的 receipt 核对，实验调用旧提交中未修改的 `price_evidence`、`run_fork`、`enrich`、`aggregate`，重新取得 N−1 状态和价格事件，重跑 Foundry。full 先从空缓存重新取得 Phase 1 对照窗口，再完整运行 Phase 2，最后使用相同 Phase 3 实验函数。

**没有运行时缓存适配或源码改写**。RPC_CACHE_DIR 指向临时 worktree/data/rpc，旧代码天然使用这个目录。本地代理也通过旧 rpc_cache 使用该目录。`forge test --help` 已确认支持 `--no-storage-caching`；运行设置等效的 FOUNDRY_NO_STORAGE_CACHING=true，并通过 `forge config --json` 实测为 true。FOUNDRY_CACHE_PATH、FOUNDRY_OUT、HOME/USERPROFILE 均指向临时目录，默认实验 EVM 仍为 Istanbul。

resultsHash 仅从临时目录新生成的 experiments.json、sensitivity.json 按清单投影计算。复制一份新生成证据到 deployments 下后，清理临时 worktree；不会读取本仓库的 Phase 3 结果来冒充复现。网络计数取 transport 实际发出的上游请求（包括失败能力探测和 Foundry 经代理请求），不把缓存命中计入；零请求禁止作为有效复现。报告仅写 RPC URL 的 SHA-256，不写 URL 或凭据。

### 实际 quick 结果

结果运行中，完成后填写。

前两次网络实验均未完成：第一次 957 次上游请求、931.188 秒，在第 10 个账户的 Foundry 执行失败；第二次 2 次请求、61.005 秒，样本 receipt 请求 SSL 握手超时。报告和日志分别保存在 incomplete 与 network-failure 文件。第一次旧版失败处理未保留临时 forge 详细日志，不能据此确定具体网络错误；新版保留部分证据与诊断，并只对明确的只读网络错误最多尝试三次，不忽略计算断言。上述均不构成成功复现。

## 上下文核验发现

清单七个 scriptSha256 与禁用换行符转换后的旧提交均一致，Python 3.14.6 / Cast 1.8.5 / Forge 1.8.5 与清单完全相同。但按旧 `phase3_batch.implementation()` 的九个文件顺序计算：

- 清单 phase3ImplementationSha256：`68cd1b188c3411beed89c07d4548b87cf1cc29dd9b554c966931371362c71401`
- 精确 script_commit 实际 SHA-256：`da1476c7811c4e02766b1c739586b719ebd2656956430167ac4cfdf1465b8e86`

这项原有清单内部上下文差异不会通过修改旧源码或忽略指纹来消除。即使新结果哈希相等，也只能判 CONTEXT_DIFFERENT，不发 attest。单文件哈希及运行中 Forge 配置核验见 `deployments/reproduction-context-audit.json`。首次因本地 core.autocrlf=true 而失败的前置检查另存为 `deployments/reproduction-quick-v1-context-crlf.json`，那次没有运行实验或发送 attest。

清单没有保存原 RPC URL 哈希，无法证明供应商 URL 与当时相同。报告明确记载这一限制；可核对的是 Ethereum chain ID=1、样本区块和日志内容。四种科学判定依次为 NOT_COMPARABLE（清单/schema 不通过）、CONTEXT_DIFFERENT（上下文不符）、MATCH、MISMATCH；只有后两者可上链，提交本次重新计算的 resultHash。执行中断无完整结果时 status=null、execution_status=FAILED，不伪造科学判定。

## 离线测试和原证据保护

```powershell
python -m unittest discover -s test -p "test_register*.py" -v
python -m unittest discover -s test -p "test_reproduce*.py" -v
python test/test_reproduce_cache_regression.py
```

25 项单元测试通过，覆盖清单哈希失败、结果 MISMATCH、CONTEXT_DIFFERENT 不上链、主网直接退出、链 ID 非 968 拒绝发送、配置白名单及不读取主网变量、缓存目录覆盖和分段缓存、重复登记拒绝、MISMATCH 提交 false 与实际结果哈希。

缓存回归在另一个临时副本使用原缓存进行，目的仅是验证改动默认行为，不计入独立复现：Phase 2 `--cache-only` 零 RPC 请求、13882 命中；Phase 3 `--cache-only` 零 RPC 请求、2506 命中。Phase 2 events/accounts/summary、Phase 3 sensitivity 文件与原文件逐字节相同，resultsHash 投影也逐字节相同。rpc_cache.py 属于 Phase 3 源码指纹输入，其改动会导致 experiments.json 的 implementation/input/result 指纹元数据变化，因此**不声称完整 experiments.json 字节相同**。没有重新生成或提交本仓库 data/phase1–4；回归证据保存于 `deployments/cache-only-regression.json`。

## 后续主网切换

本版的 `--network mainnet` 明确报错，不存在主网发送路径。正式切换前需要单独授权的新任务：先解决并重新发布清单上下文一致性问题；为 mainnet 实现独立配置和 chain ID=677 的严格发送门槛、部署记录与登记日志；补足主网部署者余额并验证编译参数；完成离线防错测试和只读预检；获得主网广播授权后部署、登记调查并独立复现。该后续实现完成后，用户入口可保持仅将 `--network testnet` 改成 `--network mainnet`。不能只改当前常量或拿测试网地址作为比赛有效部署。
