# Phase 4：假设与审核 Agent

## 当前状态：按校验规则停止

假设选择已通过；审核模型初次输出和两次重试均未通过，因此没有生成 report.json、report.md 或 manifest.json。不得将缓存中的候选报告当作有效报告。
所用模型：`deepseek-v4.1-flash`。完成五次实际 LLM 请求；另有两次沙箱网络失败。凭据未写入缓存或日志。

## 运行命令

```powershell
python -m unittest discover -s test -p "test_phase4*.py" -v
python scripts/phase4_run.py --verify-replay
python scripts/phase4_run.py --cache-only
```

只使用 Python 标准库，通过 urllib 向 `{LLM_BASE_URL}/chat/completions` POST，启用 JSON 模式。
LLM_BASE_URL、LLM_MODEL、LLM_API_KEY 都从 .env 读取；缺少任意字段立即停止。
一键生成要求整个工作区干净，读取 HEAD 作为 manifest.script_commit；生成过程中其他会话改动或提交也会导致停止。
当前另有 Phase 5a 留下的 out-botchain/ 未跟踪目录，不在本任务可修改范围，未擅自删除、移动或忽略。
修正提示词并再次调用模型必须在用户确认继续之后进行；本次已遵守重试上限停止。
当前实现提交：`ba031ad87b1478659a2704c4dd3c2ea1fc8512d7`。清单未生成，故不存在 manifest.script_commit。

## 校验和缓存

每次请求按 SHA-256(model, prompt, input) 缓存，输入包含重试反馈，因此每次反馈有独立键；缓存保存请求正文和模型响应文本，不保存认证头。
数字和账户、区块一律使用 {{ref:文件#/JSON/Pointer}}，模板价格参数也使用引用。解析先检查裸数字、引用存在性、非空 evidence_refs，再验证封闭模板、实际实验覆盖和必需报告字段。
固定词白名单：N−1、Compound v2、2020-11-26、Phase 3、H1、H2、H3、H4。拒绝 UI_MOCK。
审核必需结论的文字、状态、证据和账户来自确定性事实契约；模型负责逐条解释和不确定性。
实际拦截共四次：

- 假设第一次：引用 summary.json 中不存在的 /unavailable_features/0。反馈后第二次通过。
- 审核第一次：解释直接写出 ±0.0001，没有引用。
- 审核第二次、第三次：顶层输出 required_sections 包装对象，未直接输出 sensitivity_summary、assumptions_and_limitations、unverified_hypotheses 等必需字段。

离线测试 29 项全部通过，包括拒绝裸数字/无效引用/缺证据/非法模板参数/UI_MOCK，实际实验覆盖，三次失败停止，缓存重放零网络，哈希元数据隔离与复现状态。
实际完整第二次运行未执行；没有三个合格主输出，因此不能宣称三个 SHA-256 不变。

## 假设 Agent 结果

- H1 / EXPERIMENT_COVERED：DAI 相关借款人和事件在汇总中占主导，cDAI 市场汇总规模最大，且存在唯一模板 dai_price_override 可用于价格覆盖敏感性实验，因此值得实验；实验覆盖不等于原因已验证。
  模板：`dai_price_override`；prices：1.00, 1.05, 1.10, 1.20, 1.30
- H2 / UNVERIFIED：summary 仅以 N−1 预言机价格估值用于排序，并说明不等于清算实际价格；未提供抵押品真实下跌的直接特征，且无对应实验模板，因此不值得实验。
- H3 / UNVERIFIED：summary 结构化字段未包含协议参数变更的证据或比较维度，且无对应实验模板，因此无法从现有特征判断，不值得实验。
- H4 / UNVERIFIED：summary 未提供前排账户信息或日内分布；仅有借款人及事件汇总计数，无法归因于借款人自身操作，且无对应模板，因此不值得实验。

模型说其他假设“不值得实验”仅是本阶段选择理由；现有摘要缺少对应特征或模板，不代表这些原因被排除。
summary.json 不含日内时间直方图和前二十账户明细，未向假设模型提供或编造这些信息。

## 审核结论

没有通过校验的审核结论。三个候选响应仅作为失败证据保存在 data/phase4/llm/，不得发布为正式报告。
后续合格报告必须覆盖低价档的不可清算结果、临界价分布、N−1 已有缺口、真实组未复现、其他资产改价诊断、未解释账户、不适用账户和估值口径；对应检查已写入脚本和测试。

## 哈希

- manifestHash：未生成。
- resultsHash：`0xb40a7ca6f32cf9d8491fd864826f010649dbfe6b78ee16310ef8f2666000f139`
- caseId 哈希：`0x51aec3f6bc0c3ac98b0c63e7e15252ce548cfeeb15f780e4c744b6fefcbba2ef`

五个向量（空串、abc、含中文 JSON、大型 experiments.json、caseId 原文）均与本地 cast keccak 完全一致，详情见 data/phase4/status.json。
规则名 keccak256-jcs，严格按 sort_keys=True、separators=(",", ":")、ensure_ascii=False 序列化为 UTF-8，再计算 Keccak-256（不是 SHA3-256）。
拒绝浮点、NaN、重复键、非字符串键；绝对值大于 2^53 的整数必须预先转成字符串。此名称指本项目约定，不宣称通用 RFC 8785 实现。
resultsHash 只对 {experiments: 账户投影数组, sensitivity: sensitivity.rows} 计算。账户仅保留 borrower、sample_event、groups、critical_price、status，保留数组顺序。
递归删除 scripts/phase4_manifest.py 中 RESULTS_DEFINITION.recursiveExcludedKeys 明列的 provenance、时间、耗时、请求计数等字段；其他账户字段及诊断、LLM 解释不纳入。
完整结果文件哈希仍包括其 provenance，与独立实验复现比较用的 resultsHash 分开。manifestHash 应对完整 manifest 计算，自身不得写入清单避免循环。

## 复现状态（Phase 5g）

| 状态 | 判定 | 上链行为 |
| --- | --- | --- |
| MATCH | 清单哈希通过、上下文相同、resultsHash 一致 | matched=true |
| MISMATCH | 清单哈希通过、上下文相同、resultsHash 不一致 | matched=false |
| CONTEXT_DIFFERENT | RPC、工具版本或 commit 不同 | 不上链，只写本地报告 |
| NOT_COMPARABLE | 清单哈希不符或 schema 不支持 | 不上链 |

先用可信发布渠道提供的 expected manifestHash 校验原始清单和冻结文件，再在独立目录及清单指定的 script_commit 上复现实验。
Phase 5g 独立复现须隔离并清空自己的 RPC/Foundry 缓存，勿删除本仓库证据。Phase 4 缓存重放只验证模型结果和哈希，不能代替独立链上实验。
上下文应显式记录不含凭据的 RPC 标识、工具版本与 commit。本阶段不访问 BOT Chain，不发送交易。

## 假设与局限

- 单变量假设：正式组只改 DAI 价格，其他资产保持 N−1。
- N−1 是近似状态，没有重放区块 N 的早先交易或账户操作。
- getAccountLiquidity 不计提利息；真实清算会计提借款和抵押市场利息，缺口不等于交易内精确缺口。
- 只用首次清算，清算次数按全部事件计。
- 临界价格是推导值，固定其他价格并验证 ±0.0001 美元符号翻转。
- 1.00 美元是锚定价格，不是当时的市场价。
- 不据此认定操纵或整个事件的单一原因。
- 补实验回路未实现。
- 假设输入缺少日内分布和前排账户明细。
- 模型响应未通过审核结构约束；正式报告及清单尚未完成。
- 当前输出只能用于开发及失败追踪，不能登记上链。
