# Phase 3：批量反事实实验与敏感性

通过 14；真实组未复现 5；不适用 1。Phase 1 回归：exact_match。

## 运行

```powershell
python scripts/phase3_batch.py
python scripts/phase3_batch.py --cache-only
# 强制重跑 Foundry，同时禁止上游请求：
python scripts/phase3_batch.py --cache-only --rerun-fork
```

只依赖 Python 标准库和项目现有 Foundry/Solidity。RPC 复用 rpc_cache 和 rpc_transport 全局 0.22 秒间隔。每个区块优先读取 eth_getBlockReceipts；不支持时逐笔读取至该区块所选样本中最晚的交易，失败能力探测也持久化。区块收据按交易位置完整核对，日志按清算位置截断，包括同交易的更早日志。价格来源是动态预言机的最后一次 PriceUpdated；无 DAI 更新时使用 N−1 状态并明确标记。

每账户一次 forge 运行，包含参考、真实、五档敏感性、临界价上下验证和条件诊断组。每组先 clearMockedCalls，再 mock 并回读；动态验证 oracle、DAI underlying 和 decimals。检查点包含输入/代码指纹和结果哈希；中断后复用已完成账户、RPC 和收据缓存。单账户收据或 fork 超过 25 分钟即停止并保留缓存。

## 请求与耗时

| 运行 | 状态 | RPC 请求尝试数 | RPC 缓存命中 | 账户结果命中 | 秒数 |
| --- | --- | ---: | ---: | ---: | ---: |
| 1 | failed | 1 | 6 | 0 | 0.437 |
| 2 | failed | 1 | 11 | 0 | 2.847 |
| 3 | passed | 1929 | 591 | 0 | 1811.236 |
| 4 | passed | 0 | 2506 | 0 | 34.118 |
| 5 | passed | 0 | 0 | 20 | 2.203 |
| 6 | passed | 0 | 2506 | 0 | 29.982 |
| 7 | passed | 0 | 0 | 20 | 2.185 |

累计请求尝试 1931 次；累计脚本耗时 1883.008 秒（不含开发与审批等待）。

请求计数沿用 transport 的启动尝试计数，含失败尝试；沙箱阻止的尝试不代表请求已到达上游。runs.json 保留初期运行错误，不隐藏重试成本。Phase 2 状态刷新始终使用 --cache-only 并断言请求数为零。

## 每账户结果

| 排名 | 地址 | N | 次数 | 实际 DAI 美元价 | 真实 shortfall 美元 | 1.00 shortfall 美元 | 临界价（推导） | 状态 |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | `0x909b443761bbd7fbb876ecde71a37e1433f6af6f` | 11333037 | 1 | 1.095299 | 61,726.55 | 0.00 | 1.090083005770537829 | passed |
| 2 | `0xb1adceddb2941033a090dd166a462fe1c2029484` | 11333040 | 8 | 1.134249 | 548,084.14 | 0.00 | 1.122266775909015406 | passed |
| 3 | `0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42` | 11333019 | 6 | 1.0575 | 11,277.48 | 0.00 | 1.05606924168470693 | passed |
| 4 | `0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c` | 11333047 | 1 | 1.238179 | 51,166.62 | 0.00 | 1.221144645869215437 | passed |
| 5 | `0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60` | 11333050 | 1 | 1.238179 | 84,842.68 | 0.00 | 1.208083142681721779 | passed |
| 6 | `0x889abdd2bc0f3a884e607279ba132501698fbcd5` | 11333029 | 1 | 1.08 | 38,360.89 | 0.00 | 1.064608430054139484 | passed |
| 7 | `0xc9493738f07ddc43f1a004d4bb461fa42de23225` | 11333060 | 1 | 1.238179 | 125,191.50 | 0.00 | 1.163945757431722922 | passed |
| 8 | `0x161fac24d54698755dab0fcd65e2c883928ca724` | 11333040 | 1 | 1.134249 | 66,954.31 | 0.00 | 1.098409283136292805 | passed |
| 9 | `0x03324cfffabc10193de63186a374d7cfe932b162` | 11333019 | 1 | 1.0575 | 0.00 | 0.00 | 1.061701346892798612 | real_not_reproduced |
| 10 | `0xdf63be2e473ba04c26b1609e51d08cf0d78e0913` | 11335996 | 1 | 1.006454 | 0.00 | 0.00 | 1.016588294166032915 | real_not_reproduced |
| 11 | `0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc` | 11332948 | 1 | 1.017655 | 0.00 | 0.00 | 1.038333558175182209 | real_not_reproduced |
| 12 | `0x141f59a0283303a6b882b4d6973e418f8d75f9b3` | 11333065 | 1 | 1.238179 | 85,295.09 | 0.00 | 1.155206673966368383 | passed |
| 13 | `0xe24286adfc053f76888aa51d9a94f6c1519b4cba` | 11333053 | 1 | 1.238179 | 43,367.72 | 0.00 | 1.164401212677508919 | passed |
| 14 | `0xdac0db00fd0953d8731f86c6908366388bfcc1f8` | 11331593 | 1 | — | — | — | null | not_applicable |
| 15 | `0x339dab47bdd20b4c05950c4306821896cfb1ff1a` | 11333025 | 1 | 1.0575 | 0.00 | 0.00 | 1.06222729361312792 | real_not_reproduced |
| 16 | `0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba` | 11333040 | 2 | 1.134249 | 5,815.85 | 0.00 | 1.112736075217367937 | passed |
| 17 | `0x5c7c6d069ba232718f37c27a9549b547c359e31c` | 11333067 | 1 | 1.218147 | 10,025.05 | 0.00 | 1.182138168078320991 | passed |
| 18 | `0x57adad5729e839acd4019fc9e79c2685a42ed489` | 11331593 | 3 | 1.003998 | 0.00 | 0.00 | 1.032681114439395596 | real_not_reproduced |
| 19 | `0x01adb5a14196d302004e3a1970a8bb3183dd2565` | 11333029 | 1 | 1.08 | 165.38 | 0.00 | 1.079466426483379505 | passed |
| 20 | `0xdb16bb1e9208c46fa0cd1d64fd290d017958f476` | 11333059 | 1 | 1.238179 | 21,255.27 | 0.00 | 1.157328037035391744 | passed |

不适用账户原因：与 DAI 无关。未复现账户保留全部原始组、其他资产更新、诊断结果、同块重复清算标记与利息/状态差异说明；不改变区块或价格来满足验收。

## 敏感性

N−1 排序估值；合计这些账户全天偿还估值，不是该价格下模拟清算额或损失。

| 价格档 | 仍可清算账户数 | N−1 排序估值合计（美元） | shortfall 合计（美元） | 纳入账户总数 |
| --- | ---: | ---: | ---: | ---: |
| 1.00 | 0 | 0.00 | 0.00 | 14 |
| 1.05 | 0 | 0.00 | 0.00 | 14 |
| 1.10 | 5 | 59,116,804.91 | 561,171.81 | 14 |
| 1.20 | 12 | 84,700,713.58 | 6,723,029.87 | 14 |
| 1.30 | 14 | 93,185,405.05 | 14,643,215.90 | 14 |
| real | 14 | 93,185,405.05 | 1,153,528.52 | 14 |

只统计真实组 err=0 且 shortfall>0 的账户；diagnostic_only 不纳入。真实组价格因样本而异。

## 临界价格分布

用 signed balance = liquidity − shortfall，按 $1.00/$1.30 两端线性插值；其余三档检验线性，容差为 $0.00000001 以容纳整数舍入。只接受临界价 ±$0.0001 从正余额到负余额的翻转；非下降敞口、非线性或未翻转均输出 null 并注明原因。

参考组 N−1 已有缺口的账户排名：5, 7, 12, 13, 17, 20。其真实组通过不能表述为本区块 DAI 更新首次触发清算。

已验证临界价 19 个；最小 1.016588294166032915，中位数 1.098409283136292805，最大 1.221144645869215437 美元。

| 区间 | 账户数 |
| --- | ---: |
| [0, 1.00) | 0 |
| [1.00, 1.05) | 3 |
| [1.05, 1.10) | 7 |
| [1.10, 1.20) | 7 |
| [1.20, 1.30) | 2 |
| [1.30, Infinity) | 0 |

## 诊断与结论边界

- `0x909b443761bbd7fbb876ecde71a37e1433f6af6f`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0xb1adceddb2941033a090dd166a462fe1c2029484`：passed；清算前非 DAI PriceUpdated 1 条；同块清算 2 次；诊断组 shortfall 232,622.34。
- `0xed3c4c5d7a9abfd74f33c1042793dfd6a6daef42`：passed；清算前非 DAI PriceUpdated 1 条；同块清算 1 次；诊断组 shortfall 11,277.48。
- `0x189c2c1834b1414a6aee9eba5dc4b4d547c9a44c`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0x39c09fdc4e5c5ab72f6319ddbc2cae40e67b2a60`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0x889abdd2bc0f3a884e607279ba132501698fbcd5`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0xc9493738f07ddc43f1a004d4bb461fa42de23225`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0x161fac24d54698755dab0fcd65e2c883928ca724`：passed；清算前非 DAI PriceUpdated 2 条；同块清算 1 次；诊断组 shortfall 64,234.80。
- `0x03324cfffabc10193de63186a374d7cfe932b162`：real_not_reproduced；清算前非 DAI PriceUpdated 1 条；同块清算 1 次；诊断组 shortfall 6,601.25。
- `0xdf63be2e473ba04c26b1609e51d08cf0d78e0913`：real_not_reproduced；清算前非 DAI PriceUpdated 1 条；同块清算 1 次；诊断组 shortfall 49,990.05。
- `0xf2df969f59b2c86e4b230da88918cdebcfc4ccbc`：real_not_reproduced；清算前非 DAI PriceUpdated 3 条；同块清算 1 次；诊断组 shortfall 0.00。
- `0x141f59a0283303a6b882b4d6973e418f8d75f9b3`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0xe24286adfc053f76888aa51d9a94f6c1519b4cba`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0x339dab47bdd20b4c05950c4306821896cfb1ff1a`：real_not_reproduced；清算前非 DAI PriceUpdated 1 条；同块清算 1 次；诊断组 shortfall 346.77。
- `0xb6c0276ad1d87c6cf6dfa323d0c3f6840121c0ba`：passed；清算前非 DAI PriceUpdated 1 条；同块清算 1 次；诊断组 shortfall 6,777.05。
- `0x5c7c6d069ba232718f37c27a9549b547c359e31c`：passed；清算前非 DAI PriceUpdated 4 条；同块清算 1 次；诊断组 shortfall 10,076.91。
- `0x57adad5729e839acd4019fc9e79c2685a42ed489`：real_not_reproduced；清算前非 DAI PriceUpdated 11 条；同块清算 1 次；诊断组 shortfall 1,590.09。
- `0x01adb5a14196d302004e3a1970a8bb3183dd2565`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。
- `0xdb16bb1e9208c46fa0cd1d64fd290d017958f476`：passed；清算前非 DAI PriceUpdated 0 条；同块清算 1 次；诊断组 shortfall 未触发。

真实组未复现只说明固定 N−1 状态下本实验未重现清算条件，不能判定链上清算无效；其他资产价格、区块内操作及利息计提可能导致差异，当前不据此认定具体原因。

## 局限

- 单变量假设：正式组只改 DAI 价格，其他资产保持 N−1。
- N−1 是近似状态，没有重放区块 N 的早先交易或账户操作。
- getAccountLiquidity 不计提利息；真实清算会计提借款和抵押市场利息，缺口不等于交易内精确缺口。
- 只用首次清算，清算次数按全部事件计。
- 临界价格是推导值，固定其他价格并验证 ±0.0001 美元符号翻转。
- 1.00 美元是锚定价格，不是当时的市场价。
- 不据此认定操纵或整个事件的单一原因。

## 来源与回归

provenance：`{'mode': 'FROZEN', 'source': 'Ethereum mainnet via cached eth_getLogs/eth_call', 'capturedAt': '2026-10-07T05:16:29.680161+00:00'}`。

全部输出含 provenance；UI_MOCK 一律拒绝。顶层 mode 表示本次读取方式，账户证据保留生成时来源。原始整数和完整美元小数见 JSON，报告金额仅显示两位。

Phase 1 回归逐字段比较原 single_account.json 的三个 groups（包括整数、美元值和价格来源）、样本交易/日志、预言机及通过状态。Phase 3 新增敏感性和临界价字段，不要求不同 schema 的整个文件字节一致。

## 最终验收记录

上游实际 RPC 请求 1930 次，新增成功 RPC 缓存文件同为 1930；另有 1 次沙箱阻止的尝试。

31 项离线测试通过。最终强制离线 Foundry 复跑 29.982 秒、零 RPC；普通重跑 2.185 秒、零 RPC、20/20 账户结果命中。

两次运行的 Phase 3 experiments/sensitivity 和 Phase 2 events/accounts/summary 共五个主文件字节完全一致；SHA-256、运行信息和统计见 data/phase3/verification.json。
