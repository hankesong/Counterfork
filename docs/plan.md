# 反事实调查员：完整方案

Oct 6, 2026 · @Rory Xiao

## 一句话定位

一组协作的 Agent 调查链上异常清算：在以太坊主网分叉上把时间拨回清算前的区块，改变一个条件（如预言机价格），检验清算是否仍然成立，用可复现的反事实实验给出“原因是什么、影响多大、多确定”的证据，结论与实验记录上链公开。

赛道：汉客松 S1 & ETH Wuhan 2026 主赛道（AI × Blockchain）+ GCC 公共物品赛道赛题二（以太坊链上异动调查 Agent）+ BOT Chain 分赛道（调查登记合约部署到主网）。

## 问题与真实案例

链上分析大多停在描述“发生了什么”，很少能用证据回答“为什么发生、如果没有这个原因会怎样”。

案例：Compound 2020 年 11 月 26 日清算事件。

| 事实 | 内容 | 来源 |
| --- | --- | --- |
| 触发 | DAI 在 Coinbase Pro 短暂冲到约 1.30 美元；Compound 的预言机以 Coinbase 价格为基准，Uniswap 作锚定校验 | [Invezz](https://invezz.com/news/2020/11/27/increased-dai-price-allowed-compound-comp-liquidator-to-earn-4-million/) |
| 规模 | Decrypt 报道 24 小时约 8,900 万美元被清算；链上实测 2020-11-26 UTC 全天 Compound v2 共 182 笔清算，按 N−1 预言机估值约 9,906 万美元，其中 DAI 相关 153 笔、约 9,687 万美元（data/phase2/summary.json） | [Decrypt](https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound) |
| 最大单笔 | 一个循环借贷的大户被清算约 4,600 万 DAI | [Invezz](https://invezz.com/news/2020/11/27/increased-dai-price-allowed-compound-comp-liquidator-to-earn-4-million/) |
| 争议 | 合约按设计运行，问题在预言机；是市场波动还是操纵，缺少量化证据 | [The Block](https://www.theblock.co/post/85850/dai-compound-dydx-liquidations-defi) |

目标用户：协议风控与治理团队、链上研究员、受影响用户（索赔或申诉时需要证据）。

## Agent 协作流程

&#91;embedded content: Agent 协作流程 · 4 个 Agent，1 个补实验回路，链上复现\]

审核 Agent 发现证据不足时，退回假设 Agent 补实验；调查清单登记上链后，任何人都能读取清单重跑，并把复现结果登记回链上。

## demo 范围

只做一个事件、一个协议、一个实验性假设；其他假设在报告中列出但不做实验。

| 维度 | 范围 |
| --- | --- |
| 事件 | Compound v2，2020-11-26 前后的清算 |
| 数据 | cDAI 等市场的 LiquidateBorrow 事件（真实主网数据，抓取后缓存到本地） |
| 实验假设 | 预言机 DAI 价格异常；对照组为 DAI = 1.00 美元 |
| 列出不做实验的假设 | 抵押品真实下跌、协议参数变更、借款人自身操作 |
| 敏感性 | DAI 按 1.00 / 1.05 / 1.10 / 1.20 / 1.30 美元分别计算 |
| 链上 | 调查记录与复现证明写入 BOT Chain 主网 |

## 实验设计

每个被清算账户做一次“真实 vs 反事实”的对照：同一个区块状态，只改 DAI 价格，比较账户是否资不抵债。

1. 定位：从 LiquidateBorrow 事件取出借款人地址和所在区块 N。
2. 分叉：用 Foundry 分叉以太坊主网到区块 N − 1（清算交易执行前的状态）。
3. 改价：用 `vm.mockCall` 让预言机的 `getUnderlyingPrice(cDAI)` 返回反事实价格；Compound 价格按 1e(36 − 标的精度) 缩放，DAI 精度为 18，所以 1.00 美元 = 1e18。
4. 查询：调用 Comptroller 的 `getAccountLiquidity(borrower)`，返回 (错误码, 剩余流动性, 缺口)；缺口 > 0 即可被清算。
5. 对照：真实价格与反事实价格下各跑一次，记录缺口变化。
6. 敏感性：对 5 个价格档位重复第 3–5 步，汇总“仍成立的清算账户数和金额”。

```solidity
vm.createSelectFork(rpcUrl, blockN - 1);
vm.mockCall(
    address(oracle),
    abi.encodeWithSelector(oracle.getUnderlyingPrice.selector, cDAI),
    abi.encode(counterfactualPrice) // 1.00 美元 = 1e18
);
(uint err, uint liquidity, uint shortfall) = comptroller.getAccountLiquidity(borrower);
```

要在报告中写明的假设与局限：

- 只改 DAI 价格，其他资产沿用真实预言机价格（单变量假设）。
- 用区块 N − 1 近似清算前状态；同一区块内若先有喂价更新，需单独核对。
- 1.00 美元是锚定价格，不是“当时的真实市场价”；其他交易所的同期价格不在链上，作为外部假设单独标注。

## AI 的分工与约束

AI 负责“提出假设”和“解释结果”，实验由确定性代码执行，结论由数据决定。

| Agent | 用不用大模型 | 做什么 |
| --- | --- | --- |
| 事件 Agent | 否 | 按区块范围抓取清算事件，整理账户、金额、区块 |
| 假设 Agent | 是 | 根据事件特征提出候选原因，并从固定的实验模板中选择（改价格、改参数），填入参数 |
| 模拟 Agent | 否 | 执行实验模板，输出每个账户的缺口 |
| 审核 Agent | 是（只写解释） | 检查每条结论是否有实验支撑，汇总敏感性结果，写白话结论和不确定性说明 |

约束：

- 实验只能从模板中选，大模型不能自己写任意代码去跑。
- 结论中的每个数字都来自模拟结果文件，审核 Agent 引用时附账户与区块号。
- 没做实验的假设标为“未验证”，不得写成结论。
- 报告必须包含“假设与局限”一节（见实验设计）。

## 链上设计与合约接口

调查登记合约（InvestigationRegistry）部署在 BOT Chain 主网，记录两件事：一份调查发布了什么，以及谁独立复现过它。

为什么上链：调查清单（分叉区块、改动、脚本版本、结果）的哈希一经登记就不能事后修改；其他人重跑后登记“复现一致/不一致”，结论的可信度来自多方独立复现，而不是发布者自己说了算。这正是公共物品赛道要的“别人能核查、能继续改进”。

```solidity
function submitInvestigation(
    bytes32 caseId,          // 例：keccak256("compound-2020-11-26-dai")
    uint256 targetChainId,   // 被调查的链，以太坊主网为 1
    uint256 fromBlock, uint256 toBlock,
    bytes32 manifestHash,    // 调查清单（规范化 JSON）的哈希
    string calldata manifestURI
) external returns (uint256 version);

function attestReproduction(bytes32 caseId, uint256 version,
    bool matched, bytes32 resultHash) external;

event InvestigationSubmitted(bytes32 indexed caseId, uint256 version, address author, bytes32 manifestHash);
event ReproductionAttested(bytes32 indexed caseId, uint256 version, address reproducer, bool matched);
```

调查清单包含：RPC 无关的分叉区块号、每个实验的模板与参数、脚本仓库的提交哈希、每个账户的结果。任何人拿到清单就能一键重跑。

## 技术栈

| 层 | 选型 | 用途 |
| --- | --- | --- |
| 数据 | 支持归档数据的以太坊 RPC（如 Alchemy 免费额度）+ viem `getLogs` | 抓取 2020-11 的清算事件，结果缓存为 JSON |
| 实验 | Foundry（forge 测试 + `vm.createSelectFork` + `vm.mockCall`） | 分叉、改价、查询账户缺口 |
| 编排 | Python 或 TypeScript | 批量生成实验、调度 forge、收集结果 |
| AI | 支持结构化输出的大模型 | 假设 Agent 选模板填参数；审核 Agent 写解释 |
| 合约 | Solidity + Foundry | InvestigationRegistry，部署 BOT Chain 主网 |
| 前端 | React + viem + 图表库 | 事件列表、单账户对照、敏感性曲线、链上记录与复现状态 |

## demo 脚本

初评每队约 6 分钟（含问答），演示控制在 3 分半内。高潮是敏感性曲线：一张图说清“结论有多依赖价格假设”。

| 时间 | 内容 |
| --- | --- |
| 0:00–0:30 | 问题：2020 年 Compound 约 8,900 万美元清算，至今没人量化回答“如果预言机价格正常会怎样” |
| 0:30–1:00 | 事件 Agent 列出该时段的全部清算账户和金额（真实数据） |
| 1:00–1:30 | 假设 Agent 列出 4 个候选原因，选定“预言机价格异常”并生成实验 |
| 1:30–2:15 | 单账户对照：最大那笔清算的账户，真实价格下缺口 > 0，DAI = 1.00 时缺口是否消失 |
| 2:15–2:45 | 敏感性曲线：5 个价格档位下仍成立的清算金额；审核 Agent 读出结论与局限 |
| 2:45–3:30 | 调查清单哈希写入 BOT Chain 主网；队友用另一台电脑重跑并登记“复现一致” |

实验结果提前跑好并缓存，现场只演示单账户实时重跑，避免归档 RPC 慢导致冷场。

## 40 小时时间表

&#91;embedded content: 40 小时时间表 · 10/6 18:00 至 10/8 13:30\]

今晚的关卡最关键：归档 RPC、预言机地址、单账户“分叉 → 改价 → 查缺口”三步全部跑通才继续；主网 Gas 今晚就联系 BOT Chain 技术联系人。

## 分工

按 3 人估计；只有 2 人时，前端只做敏感性曲线和单账户对照两页。

| 角色 | 负责 |
| --- | --- |
| 实验与合约 | 归档 RPC、Foundry 分叉实验模板、InvestigationRegistry 与主网部署 |
| 数据与 Agent | 清算事件抓取与缓存、实验编排、假设 Agent 与审核 Agent |
| 前端 | 事件列表、单账户对照、敏感性曲线、链上记录与复现状态 |
| 产品（肖雅贞） | 研读 Compound v2 清算逻辑、假设清单、报告模板与局限说明、demo 与答辩材料 |

## 提交材料清单

截止时间为 Oct 8, 2026 12:00（北京时间），目标 11:30 前提交。对照选手手册 5.2：

- [ ] 项目说明：队名与成员、项目名称、目标用户、解决的问题、核心功能、比赛期间完成的工作
- [ ] 代码仓库与运行说明：依赖、归档 RPC 配置、一键复现命令；注明沿用组件的来源
- [ ] 调查报告与调查清单（含假设与局限）
- [ ] 演示视频或可运行链接
- [ ] BOT Chain 主网：InvestigationRegistry 合约地址、区块浏览器链接、登记与复现交易

## 风险与预案

| 风险 | 预案 |
| --- | --- |
| 归档 RPC 拿不到或分叉不到 2020 年区块 | 今晚第一件事验证；不行就换题（可转 DAO 审查，环境可复用） |
| 读不懂 Compound v2 清算逻辑 | 一人专门研读 Comptroller 与 cToken；只用 getAccountLiquidity，不重放清算交易本身 |
| 归档 RPC 调用限额 | 事件与实验结果全部缓存；先跑最大的 20 个账户，再按需扩展 |
| 同一区块内的喂价更新导致 N − 1 状态不准 | 对受影响账户单独核对，在报告局限中写明 |
| 结果不支持“预言机导致” | 照实报告——方法的价值在于给出证据，不在于证明某个结论 |
| 主网 Gas 不到位 | 今晚联系 BOT Chain 技术联系人；测试网版演示视频作保底 |

## 答辩速答

| 评委可能问 | 回答要点 |
| --- | --- |
| 反事实价格 1.00 凭什么成立？ | 它是锚定价格，不是“当时真实价格”；所以我们给的是一条敏感性曲线，让读者看到结论在每个价格假设下是否成立 |
| 只改一个变量够吗？ | 单变量是有意的设计：先隔离预言机这一个因素；其他假设列为“未验证”，模板可扩展到多变量 |
| AI 在哪里起作用？ | 提出假设、选实验模板、解释结果；实验和数字由确定性代码产生，AI 不能编造结论 |
| 为什么要上链？ | 调查清单登记后不可改；他人独立复现并登记，可信度来自多方复现，而非发布者自述 |
| 和 Dune 之类的数据分析有什么区别？ | 数据分析回答“发生了什么”，反事实实验回答“如果条件不同会怎样”，是因果层面的证据 |
| 能用到别的事件吗？ | 实验模板与协议适配层分离；换协议需要写新的适配层，换事件只改区块范围和参数 |

## 参考来源

- [Decrypt：Compound 约 8,900 万美元清算](https://decrypt.co/49657/oracle-exploit-sees-100-million-liquidated-on-compound)
- [Invezz：DAI 涨价让 Compound 清算人获利约 400 万美元](https://invezz.com/news/2020/11/27/increased-dai-price-allowed-compound-comp-liquidator-to-earn-4-million/)
- [The Block：DAI 涨价引发 Compound 大规模清算](https://www.theblock.co/post/85850/dai-compound-dydx-liquidations-defi)
- [汉客松 S1 & ETH Wuhan 2026 选手手册](https://tokenark.feishu.cn/docx/Vn3hdD7s6okrftx9583cYgganMg)
