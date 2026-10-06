# Phase 0 RPC 逐请求测试表

测试只使用 `.env` 内已授权的以太坊端点。所有请求使用 POST 与 application/json，JSON-RPC 2.0；URL 均不写入报告。

`ETH_RPC_URL` 与 `CANDIDATE_RPC_2` 是 dRPC，候选 1 是 PublicNode。地址过滤为 cDAI，主题已用 cast keccak 核对。

| 端点变量 | 测试 | 方法及 params（实际值） | 实际结果 |
| --- | --- | --- | --- |
| ETH_RPC_URL | chain | `eth_chainId []` | 成功，chainId=0x1 |
| ETH_RPC_URL | range_500 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace642"}]` | eth_getLogs: RPC error code 35: ranges over 10000 blocks are not supported on free plan |
| ETH_RPC_URL | range_1 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | range_10 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace458"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | range_50 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace480"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | range_100 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace4b2"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | no_topics | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | no_address | `eth_getLogs [{"topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | no_filters | `eth_getLogs [{"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| ETH_RPC_URL | block_hash | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"blockHash":"0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3"}]` | 成功，日志数 0 |
| ETH_RPC_URL | historical_block | `eth_getBlockByNumber ["0xace44f",false]` | 成功，区块哈希 0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3 |
| CANDIDATE_RPC_1 | chain | `eth_chainId []` | 成功，chainId=0x1 |
| CANDIDATE_RPC_1 | range_500 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace642"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | range_1 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | range_10 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace458"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | range_50 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace480"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | range_100 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace4b2"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | no_topics | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | no_address | `eth_getLogs [{"topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | no_filters | `eth_getLogs [{"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code -32602: Archive requests require a personal token. Get one at: [redacted URL] |
| CANDIDATE_RPC_1 | block_hash | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"blockHash":"0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3"}]` | 成功，日志数 0 |
| CANDIDATE_RPC_1 | historical_block | `eth_getBlockByNumber ["0xace44f",false]` | eth_getBlockByNumber: RPC error code 4444: pruned history unavailable: requested 11330639, earliest available 15500000 |
| CANDIDATE_RPC_2 | chain | `eth_chainId []` | 成功，chainId=0x1 |
| CANDIDATE_RPC_2 | range_500 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace642"}]` | eth_getLogs: RPC error code 35: ranges over 10000 blocks are not supported on free plan |
| CANDIDATE_RPC_2 | range_1 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | range_10 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace458"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | range_50 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace480"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | range_100 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace4b2"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | no_topics | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | no_address | `eth_getLogs [{"topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | no_filters | `eth_getLogs [{"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: RPC error code 27: Unknown state. First available state is 1 |
| CANDIDATE_RPC_2 | block_hash | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"blockHash":"0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3"}]` | 成功，日志数 0 |
| CANDIDATE_RPC_2 | historical_block | `eth_getBlockByNumber ["0xace44f",false]` | 成功，区块哈希 0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3 |
| CANDIDATE_RPC_3 | chain | `eth_chainId []` | eth_chainId: invalid or null response |
| CANDIDATE_RPC_3 | range_500 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace642"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | range_1 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | range_10 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace458"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | range_50 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace480"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | range_100 | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace4b2"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | no_topics | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | no_address | `eth_getLogs [{"topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | no_filters | `eth_getLogs [{"fromBlock":"0xace44f","toBlock":"0xace44f"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | block_hash | `eth_getLogs [{"address":"0x5d3a536E4D6DbD6114cc1Ead35777bAB948E3643","topics":["0x298637f684da70674f26509b10f07ec2fbc77a335ab1e7d6215a4b2484d8bb52"],"blockHash":"0x406c4ba4b0b9e404a359b53a5738ea69c8cc8d2e1623869eb31d7c10814196c3"}]` | eth_getLogs: invalid or null response |
| CANDIDATE_RPC_3 | historical_block | `eth_getBlockByNumber ["0xace44f",false]` | eth_getBlockByNumber: invalid or null response |

补充复核：候选 3 的 eth_chainId 响应为 HTTP 525，Content-Type 为 application/json; charset=utf-8，返回 Cloudflare 错误对象（status=525），不符合 JSON-RPC。初始矩阵逐项保留当时实际报告的 invalid or null response，没有倒填未记录的 HTTP 状态。

范围参数验证：fromBlock = 0xace44f；跨度 1/10/50/100/500 的 toBlock 依次为 0xace44f / 0xace458 / 0xace480 / 0xace4b2 / 0xace642。均为无前导零十六进制。blockHash 请求没有混用 fromBlock/toBlock。

最终非空验收：dRPC 的 blockHash 查询在区块 11333058 返回 1 条 cDAI LiquidateBorrow，交易收据 status=0x1 且包含完全匹配的事件。样本与重跑统计分别见 data/phase0/sample.json、data/phase0/sample_runs.json。

rpcfree：urllib 和 cast 限速代理的上游观测均为 HTTP 200 / text/html / Free Ethereum RPC — No Signup, No API Key；cast 原生直连退出码 1，报 deserialization error: expected value at line 1 column 1。仅保存元数据与标题，不保存 HTML 正文。
