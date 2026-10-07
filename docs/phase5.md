# Phase 5a / 5b：InvestigationRegistry 与主网预检

2026-10-07。主网只做读取与部署模拟，**未广播任何链 677 交易，未部署主网合约**。测试网已完成真实交易彩排；它不是比赛有效部署。

## 合约与接口

`src/InvestigationRegistry.sol` 使用 Solidity 0.8.30，无管理员、不可升级、无 payable 入口，无外部调用。任何人可提交任意 caseId（包括零值），不对 caseId 预留所有权。合约只登记声明，不验证清单内容；可信度来自多方独立复现。公开登记并不保证复现者是独立主体。

| 接口 | 行为 |
| --- | --- |
| `submitInvestigation(bytes32,uint256,uint256,uint256,bytes32,string) → uint256` | caseId 内版本从 1 递增，只追加；区块范围可相等，manifestHash 和 URI 不得为空 |
| `attestReproduction(bytes32,uint256,bool,bytes32)` | 版本必须存在，resultHash 非零；每个地址对同一 caseId/version 只能登记一次，true/false 都保留 |
| `latestVersion(bytes32) → uint256` | 未提交的 caseId 返回 0 |
| `getInvestigation(bytes32,uint256) → Investigation` | 返回 author、targetChainId、fromBlock、toBlock、manifestHash、manifestURI、timestamp、blockNumber |
| `attestationCount(bytes32,uint256) → uint256` | 该版本的复现记录数量 |
| `getAttestation(bytes32,uint256,uint256) → Attestation` | 索引从 0 开始；返回 reproducer、matched、resultHash、timestamp、blockNumber |
| `hasAttested(bytes32,uint256,address) → bool` | 该地址是否已登记 |

除 latestVersion 外，带 version 的读取接口在版本不存在（含 0）时统一 revert `InvestigationNotFound`；索引越界 revert `AttestationIndexOutOfBounds`。其他自定义错误：`InvalidBlockRange`、`EmptyManifestHash`、`EmptyManifestURI`、`AlreadyAttested`、`EmptyResultHash`。

事件保持规格中的顺序、类型和索引方式，**仅 caseId indexed**：

```solidity
event InvestigationSubmitted(bytes32 indexed caseId, uint256 version, address author, bytes32 manifestHash);
event ReproductionAttested(bytes32 indexed caseId, uint256 version, address reproducer, bool matched);
```

## 编译与测试

default profile 原有字节内容保持不变，仍为 Istanbul。新增 botchain profile：`.tools/solc.exe`（0.8.30）、Paris、optimizer=true、runs=200。编译输出、编译缓存和广播工件都隔离在 `out-botchain/`，避免改写历史实验的 `cache/`。

PowerShell，在仓库根目录运行：

```powershell
$env:FOUNDRY_PROFILE = 'botchain'
& .tools/foundry/forge.exe test --match-contract InvestigationRegistryTest -vv
python script/phase5.py regression
python script/phase5.py local
python script/phase5.py preflight
```

合约测试：**15 passed，0 failed**，其中 fuzz 256 runs。覆盖版本递增、旧记录不变、caseId 独立、零 caseId、非法输入、相等区块边界、完整读取、事件 ABI、不存在版本、重复复现、不同复现者、两种 matched 值、复现作用域、空 resultHash 后可重试和越界读取。使用原生 Vm 接口，没有 forge-std。

default profile 离线回归：**Phase1Test 1 passed，0 failed**。将原样 foundry.toml、Phase1 测试及编译器复制到临时目录，用 `FOUNDRY_PROFILE=default forge test --match-path test/Phase1.t.sol -vv --offline` 执行。所有测试输出写在临时目录，原 `data/`、`scripts/` 和其他测试文件没有改动。

回归使用只有本地读取能力的缓存代理：89 次缓存命中，0 次上游请求。节点可选能力探测（anvil_nodeInfo 两次、eth_getAccountInfo 一次）缓存未命中时返回错误，Foundry 正常回退到已缓存标准调用；没有网络回源路径。生成的 fork_result 与历史 JSON 完全一致。证据：`deployments/phase1-offline-regression.json`。

## Anvil 本地端到端

`script/phase5.py local` 启动仅绑定 127.0.0.1 的 Anvil，确认链 31337，将默认测试账户私钥从启动输出捕获到内存，以环境变量交给 `DeployRegistry.s.sol`。私钥不写入 `.env`、代码、配置或输出。部署脚本只通过 `vm.envUint("BOT_PRIVATE_KEY")` 读取私钥并创建合约。

用 cast send 调用两次登记，cast call 读回全部接口，cast receipt 核对交易成功及两个事件的 emitter、topic0、caseId 和全部非索引数据；以区块头核对 timestamp/blockNumber，并比较完整 ABI 编码。脚本无论成功或失败都在 finally 中关闭自己启动的 Anvil。

本地合约：`0x5fbdb2315678afecb367f032d93f642f64180aa3`，仅存在于已关闭的本地链。

| 操作 | 交易哈希 | status | gasUsed |
| --- | --- | --- | ---: |
| submit | `0xf6360471c0bb9e0ec2f7891b6dbaf9d2431c6691eb22410249e21ed9619426c0` | 1 | 270864 |
| attest | `0x42452ded11108365f5653a270fa1cbe4c08587ef9b797d82a96f83bcfa22f0a6` | 1 | 160692 |

公共测试参数：caseId 由 `cast keccak "compound-2020-11-26-dai"` 得到 `0x51aec3f6bc0c3ac98b0c63e7e15252ce548cfeeb15f780e4c744b6fefcbba2ef`；targetChainId=1、fromBlock=100、toBlock=200、version=1、matched=true；URI 为 `https://example.invalid/TEST-ONLY/phase5-manifest.json`，两个哈希由明确的 TEST ONLY 文本计算。这里的 targetChainId=1 表示调查对象，不是交易发送链。

读回 latestVersion=1、attestationCount=1、hasAttested=true。两个事件和完整记录已通过检查。完整 receipt、哈希、读回与事件证据见 `deployments/anvil-phase5.json`。

## BOT Chain 测试网彩排

**测试网彩排，不是比赛有效部署。** RPC 为 `https://rpc.bohr.life`，实际 cast chain-id=968，浏览器为 `https://scan.bohr.life`。脚本只使用 BOT_TESTNET_* 变量，变量缺失时使用本任务明确提供的这三个测试网默认值，不修改 `.env`。不会回退到 BOT_RPC_URL 或 ETH_RPC_URL。

```powershell
python script/phase5.py testnet
```

该命令会真实广播到链 968；已完成彩排后再次执行会因已存在部署记录而停止，防止意外重复部署。每笔 cast send 先保存交易哈希，再等待 receipt。若中断，先检查 `deployments/botchain-testnet.json` 与 `out-botchain/broadcast/DeployRegistry.s.sol/968/` 中的工件，不要直接重新广播。

部署者（与主网预检相同）：`0xea68b4bFdEd757281911520b03374B9E7D70043a`。

合约：[0x797d1f34d8946e5f19acae8ff0ea47b7763d8607](https://scan.bohr.life/address/0x797d1f34d8946e5f19acae8ff0ea47b7763d8607)。此地址只确认在链 968 部署。

| 操作 | 交易哈希 | status | gasUsed |
| --- | --- | --- | ---: |
| 部署 | `0x865a4704ea4dffa97a47760236e95e3e191ef4a617b0c6b058aa0ecec5920385` | 1 | 725259 |
| submit | `0xe1805e0b56b01fadc72b91de0f18538858fd8babcb60cf5a3744619145d10726` | 1 | 270864 |
| attest | `0xb631c964a719dda14b644b4dd219082c7728db9b3a467118808a27dcef9ee226` | 1 | 160692 |

初始余额 10，结束余额 9.9768637 测试网原生币。测试参数与本地相同，版本 1，复现数量 1，matched=true。全部字段（含两笔交易的时间戳和区块号）、两个事件均验证通过；完整证据见 `deployments/botchain-testnet.json`。复现由同一部署地址提交，仅用于功能彩排，不作为独立复现证据。

## 主网只读预检

证据：`deployments/botchain-preflight.json`。

| 项目 | 实测结果 |
| --- | --- |
| BOT_CHAIN_ID 与 cast chain-id | 均为 677 |
| 部署者 | `0xea68b4bFdEd757281911520b03374B9E7D70043a` |
| 余额 | 0 wei / 0 原生币 |
| 部署模拟 | 成功，未加 --broadcast |
| 预估 gas | 942579（Forge 默认 gas-estimate-multiplier=130，含估算余量） |
| legacy gasPrice | 20000000000 wei，即 20 gwei |
| 预估费用 | 18851580000000000 wei，即 0.01885158 原生币 |
| 余额是否足够 | 否；还需后续登记交易所需费用 |

Forge 输出使用通用单位名 ETH，此处报告为 BOT Chain 原生币。模拟中的返回地址是基于当时 nonce 的预测值，**不是主网已部署地址**；dry-run 工件的交易 hash 为 null。

当前安装 Forge 1.8.5 的 `forge script --gas-price` 只接受 wei 整数，实测 `20gwei` 会报 `invalid digit found in string`，因此准确命令使用 `20000000000`，经济含义完全相同。cast send 支持 `20gwei`。

## 等用户确认后才执行的主网部署命令

**以下含 --broadcast 的命令本次没有执行。须先补足链 677 余额、重新预检，并获得用户确认。** 从仓库根目录的 PowerShell 执行。只把主网 RPC、链 ID、浏览器地址载入当前进程，不打印 `.env`；私钥由 Forge dotenv 与 vm.envUint 读取，不出现在命令行参数中。

```powershell
$env:FOUNDRY_PROFILE = 'botchain'
Get-Content -LiteralPath .env | ForEach-Object {
    if ($_ -match '^\s*(BOT_RPC_URL|BOT_CHAIN_ID|BOT_EXPLORER_URL)\s*=(.*)$') {
        $settingName = $Matches[1]
        $settingValue = $Matches[2].Trim().Trim([char]34).Trim([char]39)
        [Environment]::SetEnvironmentVariable($settingName, $settingValue, 'Process')
    }
}
if ($env:BOT_CHAIN_ID -ne '677' -or -not $env:BOT_RPC_URL) { throw '主网配置不完整' }
$actualChain = & .tools/foundry/cast.exe chain-id --rpc-url $env:BOT_RPC_URL
if ($LASTEXITCODE -ne 0 -or $actualChain.Trim() -ne '677') { throw '链 ID 不符，停止' }
python script/phase5.py preflight
if ($LASTEXITCODE -ne 0) { throw '预检失败，停止' }
$check = Get-Content deployments/botchain-preflight.json -Raw | ConvertFrom-Json
if ($check.status -ne 'simulated_only' -or -not $check.balance_sufficient) { throw '余额不足或模拟未完成' }

# 只有用户确认主网部署后，才执行这一行：
& .tools/foundry/forge.exe script script/DeployRegistry.s.sol --rpc-url $env:BOT_RPC_URL --chain 677 --legacy --gas-price 20000000000 --broadcast
if ($LASTEXITCODE -ne 0) { throw '部署未确认成功；先查 receipt，不要盲目重试' }
```

主网合约地址及交易哈希必须从成功 receipt 获取；不能把测试网地址或模拟返回值作为主网部署证明。此部署脚本不提交调查或复现记录。

## 源码验证（现在不执行）

已核对当前 `forge verify-contract --help`：支持 `--verifier blockscout`、`--verifier-url`、`--compiler-version`、`--num-of-optimizations`、`--evm-version`、`--chain`、`--watch` 以及 `--show-standard-json-input`。不使用 --flatten，采用 standard JSON input。

主网部署成功后，在同一 PowerShell 环境中读取真实部署 receipt，执行：

```powershell
$env:FOUNDRY_PROFILE = 'botchain'
$deployment = Get-Content out-botchain/broadcast/DeployRegistry.s.sol/677/run-latest.json -Raw | ConvertFrom-Json
$receipt = $deployment.receipts[0]
if ($receipt.status -ne '0x1' -or -not $receipt.contractAddress) { throw '缺少主网成功部署 receipt' }
$registryAddress = $receipt.contractAddress
$verifierUrl = $env:BOT_EXPLORER_URL.TrimEnd('/') + '/api/'
& .tools/foundry/forge.exe verify-contract $registryAddress src/InvestigationRegistry.sol:InvestigationRegistry --chain 677 --verifier blockscout --verifier-url $verifierUrl --compiler-version v0.8.30+commit.73712a01 --num-of-optimizations 200 --evm-version paris --watch
```

如需导出浏览器手工提交用的编译器输入，使用同样的合约、编译器和优化参数，加 `--show-standard-json-input`，省略 `--watch`。本任务没有调用验证服务，也没有声明源码已验证。

## 当前遗留事项

- 主网余额为 0，待补足部署与后续调用费用，并等待用户确认后才能广播。
- `.gitignore` 不在本任务允许修改路径中；已请求是否允许仅追加 `out-botchain/`。在得到允许前保持该文件不变，严格按路径暂存，禁止 `git add .`。
- `.env` 由用户自行维护；本次只在 `.env.example` 增加空值变量和中文注释。
