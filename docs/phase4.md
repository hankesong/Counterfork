# Phase 4：假设与审核 Agent

## 运行

```powershell
python -m unittest discover -s test -p "test_phase4*.py" -v
python scripts/phase4_run.py --verify-replay
python scripts/phase4_run.py --cache-only
```

Python 仅使用标准库。`.env` 必须含 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY；缺项立即停止。
模型：`deepseek-v4.1-flash`。POST 到配置 base URL 下的 `/chat/completions`，使用 JSON 模式。
每次请求和模型文本响应按 SHA-256(model, prompt, input) 缓存；反馈重试也是独立缓存。密钥和认证头不落盘。
首次运行要求整个工作区干净，先提交脚本；捕获当时 HEAD 为 script_commit。生成期间若其他会话改动或提交则停止。
已有 manifest 时仍要求干净工作区，验证文件哈希与脚本指纹后使用缓存重新生成并逐字节比较，保留原始 script_commit，绝不改写为重跑时 HEAD。
`--verify-replay` 在一次干净起点的运行内再执行一次仅缓存重跑，并断言三个 JSON 主文件 SHA-256 不变；不会重新标记首次生成版本。
每轮校验最多重试两次。审核 deepseek-v4.1-flash 耗尽后仅允许 glm-5.3 再一轮，仍失败立即停止；不放宽规则。拒绝裸数字、无效引用、缺失证据、非法模板参数及 UI_MOCK。
每个必需结论的文字、状态、证据和账户绑定是确定性证据契约；审核模型逐条解释，并生成不确定性文字。
固定文字白名单：N−1、Compound v2、2020-11-26、Phase 3、H1、H2、H3、H4；参数数字也使用引用。
features.json 从 Phase 2 events/accounts 精确聚合 UTC 小时事件数、偿还估值、前二十账户摘要；诊断组非 DAI 资产价格变化账户数只统计事实，不作因果判断。
constants.json 的美元临界价扰动幅度由 experiments 中 epsilon_raw 和实际价格缩放比确定性换算；未扩展固定词白名单。
审核系统提示词提供完整 JSON 骨架和类型说明，禁止 required_sections/report/data 外层包装；失败反馈含缺失字段、多余字段或违规文字路径及原文。
此前失败批次与五次模型缓存仍保留；data/phase4/llm/validation_failures.json 是历史失败记录，本次验收以 verification.json 为准。

## 哈希与清单

- script_commit：`1534471884aab536a8efaeabd088f8e6806e640c`
- manifestHash：`0xabd8759d0775d5954ee0c1ab9a5584f79d81e70f69f88ccd110db6779da1ada5`
- resultsHash：`0xb40a7ca6f32cf9d8491fd864826f010649dbfe6b78ee16310ef8f2666000f139`
- caseId：`0x51aec3f6bc0c3ac98b0c63e7e15252ce548cfeeb15f780e4c744b6fefcbba2ef`
- reportHash：`0xe44320cd966ecd3df1995b61ca1fada568e10547251a6be6f6cd9ed6adeba10b`

规范化规则 keccak256-jcs：sort_keys=True、separators=(",", ":")、ensure_ascii=False，再 UTF-8 和 Keccak-256。
这遵循本项目指定的序列化规则，不宣称实现通用 RFC 8785。浮点、NaN、重复键、非字符串键及绝对值超过 2^53 的整数均拒绝；大整数必须是字符串。
manifestHash 对完整 manifest.json 计算，自身不写入清单以避免循环；哈希记录在 verification.json。
resultsHash 只投影每个账户的 borrower、sample_event、groups、critical_price、status，以及 sensitivity.rows，保留数组顺序。
递归去掉 resultsHashDefinition.recursiveExcludedKeys 指定的来源、耗时、计数等元数据；不纳入诊断组、LLM 输出及其他账户字段。
各输入文件的完整哈希与 resultsHash 不同：完整文件哈希会随 provenance 改变。独立复现实验应比较投影后的 resultsHash。
五个 cast 交叉验证向量全部一致；向量和原始 SHA-256 见 data/phase4/verification.json。

## 复现状态（Phase 5g）

| 状态 | 判定 | 上链行为 |
| --- | --- | --- |
| MATCH | 清单哈希/schema 通过，在各阶段 producer commit 上使用指定工具及参数重跑，resultsHash 一致 | matched=true |
| MISMATCH | 同上，resultsHash 不一致 | matched=false，提交本次实际 resultsHash |
| CONTEXT_DIFFERENT | Foundry/cast、solc 或 Python 版本与清单不同 | 不上链，只写本地报告 |
| NOT_COMPARABLE | 清单哈希不符或 schema 不支持 | 不上链 |

先从链上取得 expected manifestHash，下载不可变 URI 的清单，校验 schema、冻结文件、producerCommits 的 Git 源码指纹，再在隔离临时目录中执行各阶段指定 commit。清单内部指纹与 commit 不符也属于清单校验失败。执行未完成时 status=null、execution_status=FAILED，不冒充 MATCH/MISMATCH。
Phase 5g 独立复现应隔离并清空自身 RPC/Foundry 缓存；勿清空本仓库证据。Phase 4 的 --cache-only 只复现报告和哈希，不能冒充独立链上实验复现。
上下文仅包括清单指定的各阶段 producer commit、Foundry/cast、solc、Python 版本和实验参数。RPC 不属于上下文，复现者使用自己的 Ethereum 节点正是独立性的体现；只记录 URL 的 SHA-256，不比较节点供应商或 URL，不在日志和报告中记录凭据。节点仍须通过 chainId=1 与历史 eth_call 预检，样本收据必须对应冻结事件。

## v2：来源追溯与追加发布

v1 `data/phase4/manifest.json` 原样保留。其缺陷是仅记录 `script_commit=15344718`：它是 Phase 4 报告代码的提交，并不是产生 Phase 3 结果的代码。v2 增加 `producerCommits`，每阶段包含 commit、按文件顺序拼接 Git blob 的 SHA-256 和逐文件 SHA-256；`script_commit` 改为生成 v2 清单的脚本提交。v2 的 resultsHash 与 v1 完全相同。

- v2 manifestHash：`0xcfe7939cb83e66db00afe9194a9ccdc2d9226df66cb7b748bd1e4e2e8d8b4616`
- v2 resultsHash：`0xb40a7ca6f32cf9d8491fd864826f010649dbfe6b78ee16310ef8f2666000f139`
- v2 script_commit：`e3da500941ed1e0bf7ad90fe1cf6552dfa6ccec5`
- Phase 2 Git 源码指纹：`5180c1d2ede0aa533b86a93c889f69df40671371a262c7bebba73885f190dced`
- Phase 3 Git 源码指纹：`3bb5fdb92ba118470826ed9d4ec4b623ccc979b0e6080e6c6239d06f1bd87f1b`
- Phase 4 Git 源码指纹：`00b9fc2d1c358ac1e1fae18c24c14b01d18a889eb1747653a1de72d2a08226e7`

`cast keccak` 对 v2 完整规范化 JSON 的独立交叉核验一致；v1 文件未改变，v1/v2/当前冻结 Phase 3 投影三方 resultsHash 相同。验证记录见 `data/phase4/verification-v2.json`。这项冻结证据核对不是正式 quick 复现结果。

| 阶段 | producer commit | 依据 |
| --- | --- | --- |
| Phase 2 | `0faa08c447396a5c592b3f1842abd0ac2a181cb4` | 当前 events/summary 的原始结果提交；此后 accounts 的变化仅为 Phase 3 分析状态，样本、排名、偿还估值权重逐项一致 |
| Phase 3 | `655dba3665e6e213eea920c32f4aa185eb34a0c3` | Phase 3 结果首次入库；源码在确认历史换行形式后与已记录指纹精确一致 |
| Phase 4 | `1534471884aab536a8efaeabd088f8e6806e640c` | v1 七个 scriptSha256 与此提交 Git blob 逐项完全相同 |

Phase 3 综合指纹依次包含：`scripts/phase3_batch.py`、`test/Phase3.t.sol`、`test/Phase1.t.sol`、`scripts/rpc_cache.py`、`scripts/rpc_transport.py`、`scripts/phase1_single.py`、`scripts/phase0_check.py`、`scripts/phase2_contract.py`、`foundry.toml`。

`git log` 和 `git diff 655dba36 15344718 -- <上述九文件>` 确认：只有 `foundry.toml` 被 `7c1d0889` 修改，新增 `[profile.botchain]`，包括 out/cache/broadcast 路径、Paris EVM、optimizer=true、runs=200；default profile 仍为 Istanbul。`rpc_transport.py` 在这个区间没有修改，其他七个源码文件也未修改。

另外，原始指纹按工作区字节计算，而 Git 使用了换行符规范化。原工作区 `scripts/phase2_contract.py` 的第 10–20、57–70、73、83 行为 LF，其余行为 CRLF；其余八文件为 LF。这个混合格式在当前工作区仍可核验。Git blob 为纯 LF。**不存在 Git 原始 blob 指纹直接等于旧记录值的提交**，不能伪称找到了这样的提交。

| 提交 | Git blob 拼接 SHA-256 | 恢复已确认历史字节布局后的 SHA-256 |
| --- | --- | --- |
| `655dba36`、`ba031ad8` | `3bb5fdb92ba118470826ed9d4ec4b623ccc979b0e6080e6c6239d06f1bd87f1b` | `68cd1b188c3411beed89c07d4548b87cf1cc29dd9b554c966931371362c71401`（精确命中） |
| `7c1d0889`、`aec5b5bd`、`23bd94f8`、`15344718` | `da1476c7811c4e02766b1c739586b719ebd2656956430167ac4cfdf1465b8e86` | `f49bb67aa3aeef59937efc45c7a1d2ef671f5ea59a955d1d48bb9e71df500a6c` |

更早四个提交缺少 Phase 3 源文件，无法计算此综合指纹。逐提交明细、文件顺序和完整 diff 见 `data/phase4/fingerprint-audit-v2.json`，可用 `python scripts/manifest_v2.py --audit` 复核。v2 的可执行代码指纹明确以 Git blob 为准，另保留 `recordedWorkingTreeFingerprint` 解释旧记录；复现时不重写旧源码或换行符。Git archive 显式设置 core.autocrlf=false，并在执行前后逐文件验算。

生成步骤：先提交 v2 生成器、复现脚本及测试，再运行 `python scripts/manifest_v2.py`。脚本要求生成器与当前 HEAD 一致、核对全部 v1 冻结文件与 resultsHash，仅写 `data/phase4/manifest-v2.json`；已有不同内容时拒绝覆盖。之后将 v2 清单及本节哈希另行提交。这样清单指向已存在的生成代码提交，URI 指向后一个包含清单的提交，避免自引用循环。

### 网络、隔离和恢复

`reproduce.py --eth-rpc-env ETH_RPC_URL_INFURA` 从 .env 或环境选择节点。外部 `replay_rpc.py` 本地代理负责只读上游请求，producer 仍使用其原始 transport/cache/Foundry 代码。对超时、SSL、HTTP 429/502/503/504、Infura `-32603: precondition failure` 以 2、4、8、16、32 秒退避，总计最多六次尝试；明确参数错误、unsupported method、其他 RPC 错误不重试。恢复成功的重试只计入 retries，不算终止失败。代理响应的 JSON 空白心跳使旧 transport 的 25 秒 socket 超时与 32 秒退避兼容，不改变 RPC 数据或实验顺序。

新运行使用系统临时目录，RPC/代理缓存、Foundry cache/out/home 均隔离且初始为空，开启 no_storage_caching 并核验 forge config。真实上游请求数由代理逐请求累计并原子落盘，不能以缓存命中冒充请求，也不能仅凭预检请求认定实验有效。每个账户完成后原子写 checkpoint，绑定清单、账户、样本事件和结果哈希。中断保留目录，使用报告中的 session_dir 续跑；只补跑缺失账户，检查输入、源码、工具与 harness 不变。累计请求、重试及各次运行耗时写入报告。

```powershell
python scripts/reproduce.py --network testnet --eth-rpc-env ETH_RPC_URL_INFURA --probe-rpc
# 用户 push 包含 v2 的提交后执行：下载清单并核对哈希，然后追加版本 2
python scripts/register.py check --network testnet --version 2
python scripts/register.py submit --network testnet --version 2
python scripts/reproduce.py --network testnet --case compound-2020-11-26-dai --version 2 --level quick --eth-rpc-env ETH_RPC_URL_INFURA --attest
# 中断后在同一命令追加 --resume <报告中的 session_dir>
```

quick 重跑 Phase 3，Phase 2 选择和权重来自其 producer commit 的已哈希输入，不声称重新扫描全天或重跑 Phase 4 的 LLM。full 分别执行 Phase 2 和 Phase 3 producer；LLM 文本不在 resultsHash 内。版本 2 登记要求链上 latestVersion 恰为 1；登记后校验完整记录、事件和版本 1 的 ABI 读回保持不变。只有 MATCH/MISMATCH 才对 `(caseId, 2)` attest。测试网 chainId=968 限制保持有效。

本次 Infura 最小预检通过：区块 11333000 的 cDAI decimals() 返回 8；2 次真实请求、0 次重试、2.430 秒。RPC URL SHA-256 为 `f93d98711c2b246efbdf03a2ea15843eda35ce3cfe54a9cdc0896313b86538b5`。证据在 `deployments/reproduction-rpc-preflight-v2.json`。当前尚未登记 v2 或运行其正式 quick；须先由用户 push v2 清单提交。

v2 验证：36 项相关离线测试通过（复现 17、v2 重试/来源/恢复 10、登记保护 9）。原始 `655dba36` 在独立临时目录以 solc 0.8.30 成功离线编译；RPC 缓存不存在，Foundry 隔离配置通过，编译前后源码指纹一致。原始构建产物的 compiler version 与当前 solc 0.8.30+commit.73712a01 一致；Python 3.14.6、Foundry/cast 1.8.5 完整版本字符串与 v1 一致。

## 验收记录

37 项离线测试全部通过；规范化哈希的五个向量与 cast keccak 全部一致。本次模型请求共两次，校验拦截零次；历史失败批次不计入本次。内置缓存重跑命中两次，请求零次，三个主输出的 SHA-256 不变。

```json
[
  {
    "llm_requests": "2",
    "cache_hits": "0",
    "validation_rejections": [],
    "cache_keys": [
      "8d847584e1076d6294f8039bd9c627c73f4c5ac1d33f786c167a5570e7fc983c",
      "e4e9be9faa71991ef7fd488bf189a0032b6d86e575058e23765b6c6d69e568cb"
    ],
    "rounds": [
      {
        "agent": "hypothesis",
        "model": "deepseek-v4.1-flash",
        "status": "accepted",
        "requests": "1",
        "cache_hits": "0",
        "rejections": "0"
      },
      {
        "agent": "audit",
        "model": "deepseek-v4.1-flash",
        "status": "accepted",
        "requests": "1",
        "cache_hits": "0",
        "rejections": "0"
      }
    ]
  },
  {
    "llm_requests": "0",
    "cache_hits": "2",
    "validation_rejections": [],
    "cache_keys": [
      "8d847584e1076d6294f8039bd9c627c73f4c5ac1d33f786c167a5570e7fc983c",
      "e4e9be9faa71991ef7fd488bf189a0032b6d86e575058e23765b6c6d69e568cb"
    ],
    "rounds": [
      {
        "agent": "hypothesis",
        "model": "deepseek-v4.1-flash",
        "status": "accepted",
        "requests": "0",
        "cache_hits": "1",
        "rejections": "0"
      },
      {
        "agent": "audit",
        "model": "deepseek-v4.1-flash",
        "status": "accepted",
        "requests": "0",
        "cache_hits": "1",
        "rejections": "0"
      }
    ]
  }
]
```

## 假设选择

- H1 / EXPERIMENT_COVERED：事件窗口的小时分布显示极端集中：80 与 72 两小时的事件数远高于其余小时，且 76257456.677917683105967430987376 为窗口内最大的小时估值；同时排名第一的账户 0x909b443761bbd7fbb876ecde71a37e1433f6af6f 被标记为 dai_related=true 且估值 49833822.8826528552 最大。这一集中形态与 DAI 价格侧假设一致，因此值得用唯一可用模板对 DAI 价格覆盖做实验。
  模板 `dai_price_override`；prices：1.00、1.05、1.10、1.20、1.30
- H2 / UNVERIFIED：诊断特征记录了 10 个账户在诊断组中存在非 DAI 资产价格变化，例如 0xb1adceddb2941033a090dd166a462fe1c2029484 与 ["BTC"]，这可以作为抵押品真实下跌方向的可查线索；但该特征定义仅计数、不作归因，且 诊断组存在且 prices 中至少一项非 DAI 资产的 changed_from_reference 为真；只计账户，不作归因结论。 明确不作结论，因此目前不能据此声称该假设已验证。本阶段没有对应模板，故不运行实验。
- H3 / UNVERIFIED：窗口内事件与估值高度集中在 cDAI 市场：cDAI 的 event_count=151、repay_usd_estimate=96769063.372010796505806416650262，而 cBAT 的 event_count=1。这提示需要排查协议参数（如抵押因子、清算阈值）变更的可能，但现有特征文件没有参数变更相关字段，无法在本阶段检验。本阶段没有对应模板，故不运行实验。
- H4 / UNVERIFIED：头部账户摘要显示部分账户有多次清算记录，例如 0xb1adceddb2941033a090dd166a462fe1c2029484 的 liquidation_count=8、首次清算区块 11333040、估值 23018183.710125373487193679885064，且 0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba 的 liquidation_count=2，说明借款人自身操作（如主动还款/仓位调整）是值得单独调查的方向；但摘要只给出排序用估值，无法据此判定因果。本阶段没有对应模板，故不运行实验。

## 报告及全部结论

模型：deepseek-v4.1-flash

## 结论

- **SUPPORTED** — 通过组共 14 个账户；DAI 价格为 1.00 和 1.05 美元时，仍可清算账户分别为 0 和 0。这支持固定状态下的价格敏感性，不证明预言机是整个事件的原因。
  通过组账户在 DAI 锚定价与低档位价格下均无清算，说明固定 N−1 状态下的清算条件对 DAI 价格档位敏感；仅为价格敏感性事实，不归因预言机为事件成因。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/passed/count}}`、`{{ref:data/phase3/sensitivity.json#/rows/0/price_usd}}`、`{{ref:data/phase3/sensitivity.json#/rows/1/price_usd}}`、`{{ref:data/phase3/sensitivity.json#/rows/0/liquidatable_accounts}}`、`{{ref:data/phase3/sensitivity.json#/rows/1/liquidatable_accounts}}`、`{{ref:data/phase3/experiments.json#/experiments/0/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/1/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/2/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/3/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/4/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/5/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/6/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/7/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/11/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/12/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/15/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/16/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/18/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/19/groups}}`、`{{ref:data/phase3/experiments.json#/experiments/0/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/0/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/1/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/1/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/2/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/2/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/3/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/3/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/4/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/4/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/5/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/5/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/6/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/6/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/7/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/7/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/11/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/11/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/12/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/12/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/15/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/15/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/16/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/16/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/18/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/18/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/19/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/19/sample_event/blockNumber}}`
  账户 / 清算块 N：0x909b443761bbd7fbb876ecde71a37e1433f6af6f / 11333037；0xb1adceddb2941033a090dd166a462fe1c2029484 / 11333040；0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42 / 11333019；0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c / 11333047；0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60 / 11333050；0x889abdd2bc0f3a884e607279ba132501698fbcd5 / 11333029；0xc9493738f07ddc43f1a004d4bb461fa42de23225 / 11333060；0x161fac24d54698755dab0fcd65e2c883928ca724 / 11333040；0x141f59a0283303a6b882b4d6973e418f8d75f9b3 / 11333065；0xe24286adfc053f76888aa51d9a94f6c1519b4cba / 11333053；0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba / 11333040；0x5c7c6d069ba232718f37c27a9549b547c359e31c / 11333067；0x01adb5a14196d302004e3a1970a8bb3183dd2565 / 11333029；0xdb16bb1e9208c46fa0cd1d64fd290d017958f476 / 11333059
- **SUPPORTED** — 已验证临界价格共 19 个，最小 1.016588294166032915、中位数 1.098409283136292805、最大 1.221144645869215437 美元；此分布包含真实组未复现账户，不能与仅纳入通过账户的敏感性表混为一谈。
  已验证临界价格样本跨越多档，最小与中位数、最大均在合理区间；该分布口径含未复现账户，与仅含通过账户的敏感性表口径不同，不可直接等同。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/critical/count}}`、`{{ref:data/phase4/hypotheses.json#/evidence_summary/critical/minimum}}`、`{{ref:data/phase4/hypotheses.json#/evidence_summary/critical/median}}`、`{{ref:data/phase4/hypotheses.json#/evidence_summary/critical/maximum}}`、`{{ref:data/phase3/experiments.json#/experiments/0/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/1/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/2/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/3/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/4/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/5/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/6/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/7/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/8/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/9/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/10/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/11/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/12/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/14/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/15/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/16/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/17/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/18/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/19/critical_price}}`、`{{ref:data/phase3/experiments.json#/experiments/0/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/0/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/1/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/1/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/2/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/2/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/3/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/3/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/4/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/4/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/5/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/5/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/6/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/6/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/7/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/7/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/8/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/8/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/9/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/9/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/10/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/10/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/11/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/11/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/12/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/12/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/14/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/14/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/15/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/15/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/16/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/16/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/17/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/17/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/18/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/18/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/19/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/19/sample_event/blockNumber}}`
  账户 / 清算块 N：0x909b443761bbd7fbb876ecde71a37e1433f6af6f / 11333037；0xb1adceddb2941033a090dd166a462fe1c2029484 / 11333040；0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42 / 11333019；0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c / 11333047；0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60 / 11333050；0x889abdd2bc0f3a884e607279ba132501698fbcd5 / 11333029；0xc9493738f07ddc43f1a004d4bb461fa42de23225 / 11333060；0x161fac24d54698755dab0fcd65e2c883928ca724 / 11333040；0x03324cfffabc10193de63186a374d7cfe932b162 / 11333019；0xdf63be2e473ba04c26b1609e51d08cf0d78e0913 / 11335996；0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc / 11332948；0x141f59a0283303a6b882b4d6973e418f8d75f9b3 / 11333065；0xe24286adfc053f76888aa51d9a94f6c1519b4cba / 11333053；0x339dab47bdd20b4c05950c4306821896cfb1ff1a / 11333025；0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba / 11333040；0x5c7c6d069ba232718f37c27a9549b547c359e31c / 11333067；0x57adad5729e839acd4019fc9e79c2685a42ed489 / 11331593；0x01adb5a14196d302004e3a1970a8bb3183dd2565 / 11333029；0xdb16bb1e9208c46fa0cd1d64fd290d017958f476 / 11333059
- **NOT_SUPPORTED** — 6 个账户在 N−1 已有缺口；把这些账户说成本区块 DAI 喂价首次触发清算，证据不支持。
  这些账户在参考组已呈现缺口，说明其可清算性并非由本区块 DAI 喂价首次触发；因此把全部归因于本区块首次触发的说法不被证据支持。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/preexisting/count}}`、`{{ref:data/phase3/experiments.json#/experiments/4/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/6/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/11/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/12/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/16/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/19/groups/reference}}`、`{{ref:data/phase3/experiments.json#/experiments/4/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/4/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/6/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/6/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/11/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/11/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/12/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/12/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/16/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/16/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/19/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/19/sample_event/blockNumber}}`
  账户 / 清算块 N：0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60 / 11333050；0xc9493738f07ddc43f1a004d4bb461fa42de23225 / 11333060；0x141f59a0283303a6b882b4d6973e418f8d75f9b3 / 11333065；0xe24286adfc053f76888aa51d9a94f6c1519b4cba / 11333053；0x5c7c6d069ba232718f37c27a9549b547c359e31c / 11333067；0xdb16bb1e9208c46fa0cd1d64fd290d017958f476 / 11333059
- **UNVERIFIED** — 真实组未复现 5 个账户。这只说明固定 N−1 状态的单变量实验未重现清算条件，不能认定链上清算无效。
  真实组在单变量实验中未达到清算条件，仅反映固定 N−1 近似状态未复现，不能据此断定链上清算本身无效；原因保持未验证。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/not_reproduced/count}}`、`{{ref:data/phase3/experiments.json#/experiments/8/groups/real}}`、`{{ref:data/phase3/experiments.json#/experiments/9/groups/real}}`、`{{ref:data/phase3/experiments.json#/experiments/10/groups/real}}`、`{{ref:data/phase3/experiments.json#/experiments/14/groups/real}}`、`{{ref:data/phase3/experiments.json#/experiments/17/groups/real}}`、`{{ref:data/phase3/experiments.json#/experiments/8/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/8/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/9/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/9/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/10/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/10/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/14/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/14/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/17/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/17/sample_event/blockNumber}}`
  账户 / 清算块 N：0x03324cfffabc10193de63186a374d7cfe932b162 / 11333019；0xdf63be2e473ba04c26b1609e51d08cf0d78e0913 / 11335996；0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc / 11332948；0x339dab47bdd20b4c05950c4306821896cfb1ff1a / 11333025；0x57adad5729e839acd4019fc9e79c2685a42ed489 / 11331593
- **DIAGNOSTIC_ONLY** — 其中 4 个账户在同时修改其他资产价格的诊断组中复现。该组改变多个变量，仅作诊断；H2 抵押品真实下跌仍未验证。
  诊断组同时改变多个资产变量，其复现只能作诊断线索，不能当作 H2 抵押品真实下跌已验证的证据。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/diagnostic_reproduced/count}}`、`{{ref:data/phase3/experiments.json#/experiments/8/diagnostic/result}}`、`{{ref:data/phase3/experiments.json#/experiments/9/diagnostic/result}}`、`{{ref:data/phase3/experiments.json#/experiments/14/diagnostic/result}}`、`{{ref:data/phase3/experiments.json#/experiments/17/diagnostic/result}}`、`{{ref:data/phase3/experiments.json#/experiments/8/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/8/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/9/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/9/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/14/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/14/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/17/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/17/sample_event/blockNumber}}`
  账户 / 清算块 N：0x03324cfffabc10193de63186a374d7cfe932b162 / 11333019；0xdf63be2e473ba04c26b1609e51d08cf0d78e0913 / 11335996；0x339dab47bdd20b4c05950c4306821896cfb1ff1a / 11333025；0x57adad5729e839acd4019fc9e79c2685a42ed489 / 11331593
- **UNVERIFIED** — 仍有 1 个账户未解释：0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc。诊断组也未重现清算条件，不能据此指定原因。
  该账户在真实组与诊断组均未复现清算条件，缺乏可指定的原因，保持未解释与未验证。
  证据：`{{ref:data/phase4/hypotheses.json#/evidence_summary/unexplained/count}}`、`{{ref:data/phase3/experiments.json#/experiments/10/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/10/diagnostic/result}}`、`{{ref:data/phase3/experiments.json#/experiments/10/sample_event/blockNumber}}`
  账户 / 清算块 N：0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc / 11332948
- **UNVERIFIED** — 排名 14 的账户 0xdac0db00fd0953d8731f86c6908366388bfcc1f8：与 DAI 无关，DAI 改价模板不适用。
  该账户与 DAI 无关，DAI 改价模板不适用，故不作 DAI 价格侧结论，保持未验证。
  证据：`{{ref:data/phase3/experiments.json#/experiments/13/rank}}`、`{{ref:data/phase3/experiments.json#/experiments/13/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/13/reason}}`、`{{ref:data/phase3/experiments.json#/experiments/13/status}}`、`{{ref:data/phase3/experiments.json#/experiments/13/sample_event/blockNumber}}`
  账户 / 清算块 N：0xdac0db00fd0953d8731f86c6908366388bfcc1f8 / 11331593
- **SUPPORTED** — 敏感性表的估值合计是账户全天偿还额的 N−1 排序估值，不是在该价格下会被清算的金额，也不是损失。
  敏感性表与实验文件的估值口径一致，均为账户全天偿还额的 N−1 排序估值，不应解读为该价格下的清算额或损失。
  证据：`{{ref:data/phase3/sensitivity.json#/valuation_note}}`、`{{ref:data/phase3/experiments.json#/valuation_note}}`、`{{ref:data/phase3/experiments.json#/experiments/0/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/0/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/1/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/1/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/2/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/2/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/3/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/3/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/4/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/4/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/5/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/5/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/6/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/6/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/7/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/7/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/11/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/11/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/12/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/12/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/15/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/15/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/16/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/16/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/18/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/18/sample_event/blockNumber}}`、`{{ref:data/phase3/experiments.json#/experiments/19/borrower}}`、`{{ref:data/phase3/experiments.json#/experiments/19/sample_event/blockNumber}}`
  账户 / 清算块 N：0x909b443761bbd7fbb876ecde71a37e1433f6af6f / 11333037；0xb1adceddb2941033a090dd166a462fe1c2029484 / 11333040；0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42 / 11333019；0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c / 11333047；0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60 / 11333050；0x889abdd2bc0f3a884e607279ba132501698fbcd5 / 11333029；0xc9493738f07ddc43f1a004d4bb461fa42de23225 / 11333060；0x161fac24d54698755dab0fcd65e2c883928ca724 / 11333040；0x141f59a0283303a6b882b4d6973e418f8d75f9b3 / 11333065；0xe24286adfc053f76888aa51d9a94f6c1519b4cba / 11333053；0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba / 11333040；0x5c7c6d069ba232718f37c27a9549b547c359e31c / 11333067；0x01adb5a14196d302004e3a1970a8bb3183dd2565 / 11333029；0xdb16bb1e9208c46fa0cd1d64fd290d017958f476 / 11333059
- **UNVERIFIED** — H2 未开展对应实验，保持未验证。
  H2 在本阶段没有对应实验模板可运行，仅存在诊断线索，故保持未验证。
  证据：`{{ref:data/phase4/hypotheses.json#/hypotheses/1}}`
- **UNVERIFIED** — H3 未开展对应实验，保持未验证。
  H3 涉及协议参数变更方向，现有冻结特征中无相关字段，无法检验，保持未验证。
  证据：`{{ref:data/phase4/hypotheses.json#/hypotheses/2}}`
- **UNVERIFIED** — H4 未开展对应实验，保持未验证。
  H4 关于借款人自身操作，仅有排序用估值摘要，无法判定因果，保持未验证。
  证据：`{{ref:data/phase4/hypotheses.json#/hypotheses/3}}`

## 敏感性

N−1 排序估值；合计这些账户全天偿还估值，不是该价格下模拟清算额或损失。

| 价格档 | 可清算账户 | 纳入账户 | 全天排序估值合计 | 缺口合计 |
| --- | ---: | ---: | ---: | ---: |
| 1.00 | 0 | 14 | 0 | 0 |
| 1.05 | 0 | 14 | 0 | 0 |
| 1.10 | 5 | 14 | 59116804.913314616812024719615577 | 561171.814106875781298195 |
| 1.20 | 12 | 14 | 84700713.576378211796588761415234 | 6723029.865701883595568925 |
| 1.30 | 14 | 14 | 93185405.046504865016940936808605 | 14643215.898400029888934525 |
| real | 14 | 14 | 93185405.046504865016940936808605 | 1153528.521890625533306683 |

### 临界价格分布

| 下界（含） | 上界（不含） | 账户数 |
| --- | --- | ---: |
| 0 | 1.00 | 0 |
| 1.00 | 1.05 | 3 |
| 1.05 | 1.10 | 7 |
| 1.10 | 1.20 | 7 |
| 1.20 | 1.30 | 2 |
| 1.30 | Infinity | 0 |

## 不确定性

- N−1 为近似状态，未重放区块内早先交易与账户操作，交易内精确缺口仍有不确定性。
- getAccountLiquidity 不计提利息，真实清算会计提借款与抵押市场利息，缺口不等于交易内精确缺口，未复现原因因而未确定。
- 临界价格为推导值，仅固定其他价格并按 ±0.0001 美元验证符号翻转，线性误差容差见 0.00000001。
- 诊断组同时改变多个变量，仅作诊断，不能据此认定 H2 抵押品真实下跌已验证。
- 敏感性表估值沿用 N−1 排序口径，不代表该价格下的清算额或损失。

## 假设与局限

- 单变量假设：正式组只改 DAI 价格，其他资产保持 N−1。
- N−1 是近似状态，没有重放区块 N 的早先交易或账户操作。
- getAccountLiquidity 不计提利息；真实清算会计提借款和抵押市场利息，缺口不等于交易内精确缺口。
- 只用首次清算，清算次数按全部事件计。
- 临界价格是推导值，固定其他价格并验证 ±0.0001 美元符号翻转。
- 1.00 美元是锚定价格，不是当时的市场价。
- 不据此认定操纵或整个事件的单一原因。
- 补实验回路未实现
- 小时分布和排名账户信息由冻结事件和账户摘要确定性生成；估值仍沿用排序口径，诊断组其他资产改价仅作事实输入。
- 模型解释仅作辅助阅读；状态、引用和必需事实由确定性校验约束，仍需人工审核语义。

## 未验证假设

- H2
- H3
- H4
