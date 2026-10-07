"""One command: clean-tree preflight, cached agents, strict audit, immutable manifest."""
import argparse
import hashlib
import json
import sys
from canonical import canonical_hash, load
from phase4_common import ROOT, HYP, EXP, SENS, Client, dump, env_config, sources, render
import phase4_hypothesis
import phase4_audit
import phase4_features
from phase4_manifest import (build, cross_validate, require_clean, script_fingerprints,
                             verify_manifest, results_hash)

OUTPUTS = (HYP, 'data/phase4/report.json', 'data/phase4/manifest.json')


def sha_outputs():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in OUTPUTS}


def agents(config, cache_only):
    client = Client(config, cache_only=cache_only)
    data = sources()
    hypothesis = phase4_hypothesis.run(client, data)
    client.rounds.append({'agent': 'hypothesis', 'model': config['LLM_MODEL'], 'status': 'accepted',
        'requests': str(client.requests), 'cache_hits': str(client.hits), 'rejections': str(len(client.rejections))})
    data[HYP] = hypothesis
    report = phase4_audit.run(client, data)
    return client, data, hypothesis, report


def stats(client):
    return {'llm_requests': str(client.requests), 'cache_hits': str(client.hits),
            'validation_rejections': client.rejections, 'cache_keys': client.keys, 'rounds': client.rounds}


def write_docs(report, data, manifest, verification):
    lines = ['# Phase 4：假设与审核 Agent', '',
        '## 运行', '', '```powershell',
        'python -m unittest discover -s test -p "test_phase4*.py" -v',
        'python scripts/phase4_run.py --verify-replay',
        'python scripts/phase4_run.py --cache-only', '```', '',
        'Python 仅使用标准库。`.env` 必须含 LLM_BASE_URL、LLM_MODEL、LLM_API_KEY；缺项立即停止。',
        '模型：`' + report['model'] + '`。POST 到配置 base URL 下的 `/chat/completions`，使用 JSON 模式。',
        '每次请求和模型文本响应按 SHA-256(model, prompt, input) 缓存；反馈重试也是独立缓存。密钥和认证头不落盘。',
        '首次运行要求整个工作区干净，先提交脚本；捕获当时 HEAD 为 script_commit。生成期间若其他会话改动或提交则停止。',
        '已有 manifest 时仍要求干净工作区，验证文件哈希与脚本指纹后使用缓存重新生成并逐字节比较，保留原始 script_commit，绝不改写为重跑时 HEAD。',
        '`--verify-replay` 在一次干净起点的运行内再执行一次仅缓存重跑，并断言三个 JSON 主文件 SHA-256 不变；不会重新标记首次生成版本。',
        '每轮校验最多重试两次。审核 deepseek-v4.1-flash 耗尽后仅允许 glm-5.3 再一轮，仍失败立即停止；不放宽规则。拒绝裸数字、无效引用、缺失证据、非法模板参数及 UI_MOCK。',
        '每个必需结论的文字、状态、证据和账户绑定是确定性证据契约；审核模型逐条解释，并生成不确定性文字。',
        '固定文字白名单：N−1、Compound v2、2020-11-26、Phase 3、H1、H2、H3、H4；参数数字也使用引用。',
        'features.json 从 Phase 2 events/accounts 精确聚合 UTC 小时事件数、偿还估值、前二十账户摘要；诊断组非 DAI 资产价格变化账户数只统计事实，不作因果判断。',
        'constants.json 的美元临界价扰动幅度由 experiments 中 epsilon_raw 和实际价格缩放比确定性换算；未扩展固定词白名单。',
        '审核系统提示词提供完整 JSON 骨架和类型说明，禁止 required_sections/report/data 外层包装；失败反馈含缺失字段、多余字段或违规文字路径及原文。',
        '此前失败批次与五次模型缓存仍保留；data/phase4/llm/validation_failures.json 是历史失败记录，本次验收以 verification.json 为准。', '',
        '## 哈希与清单', '',
        '- script_commit：`' + manifest['script_commit'] + '`',
        '- manifestHash：`' + canonical_hash(manifest) + '`',
        '- resultsHash：`' + manifest['resultsHash'] + '`',
        '- caseId：`' + manifest['caseId']['hash'] + '`',
        '- reportHash：`' + manifest['reportHash'] + '`', '',
        '规范化规则 keccak256-jcs：sort_keys=True、separators=(",", ":")、ensure_ascii=False，再 UTF-8 和 Keccak-256。',
        '这遵循本项目指定的序列化规则，不宣称实现通用 RFC 8785。浮点、NaN、重复键、非字符串键及绝对值超过 2^53 的整数均拒绝；大整数必须是字符串。',
        'manifestHash 对完整 manifest.json 计算，自身不写入清单以避免循环；哈希记录在 verification.json。',
        'resultsHash 只投影每个账户的 borrower、sample_event、groups、critical_price、status，以及 sensitivity.rows，保留数组顺序。',
        '递归去掉 resultsHashDefinition.recursiveExcludedKeys 指定的来源、耗时、计数等元数据；不纳入诊断组、LLM 输出及其他账户字段。',
        '各输入文件的完整哈希与 resultsHash 不同：完整文件哈希会随 provenance 改变。独立复现实验应比较投影后的 resultsHash。',
        '五个 cast 交叉验证向量全部一致；向量和原始 SHA-256 见 data/phase4/verification.json。', '',
        '## 复现状态（Phase 5g）', '',
        '| 状态 | 判定 | 上链行为 |', '| --- | --- | --- |',
        '| MATCH | 清单哈希通过、上下文相同、resultsHash 一致 | matched=true |',
        '| MISMATCH | 清单哈希通过、上下文相同、resultsHash 不一致 | matched=false |',
        '| CONTEXT_DIFFERENT | RPC、工具版本或 commit 不同 | 不上链，只写本地报告 |',
        '| NOT_COMPARABLE | 清单哈希不符或 schema 不支持 | 不上链 |', '',
        '先从可信发布渠道取得 expected manifestHash，校验原始清单和冻结文件，再在独立目录的 script_commit 上重跑实验。',
        'Phase 5g 独立复现应隔离并清空自身 RPC/Foundry 缓存；勿清空本仓库证据。Phase 4 的 --cache-only 只复现报告和哈希，不能冒充独立链上实验复现。',
        '复现上下文应显式包含 RPC 标识、工具版本和 commit；凭据不得写入本地报告。本阶段不访问 BOT Chain，不提交交易。', '',
        '## 验收记录', '', '```json', json.dumps(verification['runs'], ensure_ascii=False, indent=2), '```', '',
        '## 假设选择', '']
    for row in data[HYP]['hypotheses']:
        lines.append('- ' + row['id'] + ' / ' + row['status'] + '：' + render(row['reason'], data))
        if row['run_experiment']:
            lines.append('  模板 `' + row['template'] + '`；prices：' + '、'.join(render(p, data) for p in row['parameters']['prices']))
    lines += ['', phase4_audit.markdown(report, data).replace('# 调查报告', '## 报告及全部结论', 1)]
    (ROOT / 'docs/phase4.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache-only', action='store_true')
    parser.add_argument('--verify-replay', action='store_true')
    args = parser.parse_args()
    config = env_config()  # Must stop for missing configuration even with cache.
    commit = require_clean()
    folder = ROOT / 'data/phase4'
    existing = (folder / 'manifest.json').exists()
    if existing:
        manifest = load(folder / 'manifest.json')
        verification = load(folder / 'verification.json')
        verify_manifest(manifest, verification['manifestHash'])
        if script_fingerprints() != manifest['scriptSha256']:
            raise ValueError('CONTEXT_DIFFERENT: scripts changed since manifest generation')
        before = sha_outputs()
    phase4_features.write_or_verify(existing=True)
    client, data, hypothesis, report = agents(config, args.cache_only)
    if existing:
        if hypothesis != load(ROOT / HYP) or report != load(folder / 'report.json'):
            raise ValueError('replayed LLM artifacts differ from frozen artifacts')
        if results_hash(data[EXP], data[SENS]) != manifest['resultsHash']:
            raise ValueError('replayed resultsHash mismatch')
        if phase4_audit.markdown(report, data) != (folder / 'report.md').read_text(encoding='utf-8'):
            raise ValueError('replayed Markdown differs')
        if before != sha_outputs():
            raise ValueError('replayed files changed')
        print(json.dumps({'replay': stats(client), 'sha256_unchanged': True,
                          'manifestHash': canonical_hash(manifest), 'script_commit': manifest['script_commit']}, ensure_ascii=True))
        return
    vectors = cross_validate()
    # Build before publishing main artifacts; only LLM caches exist at this point.
    manifest = build(commit, data, report)
    dump(ROOT / HYP, hypothesis)
    dump(folder / 'report.json', report)
    (folder / 'report.md').write_text(phase4_audit.markdown(report, data), encoding='utf-8')
    dump(folder / 'manifest.json', manifest)
    before = sha_outputs()
    verification = {'schemaVersion': '1', 'manifestHash': canonical_hash(manifest),
        'cast_vectors': vectors, 'runs': [stats(client)], 'sha256': before,
        'provenance': {'mode': 'FROZEN', 'source': 'Phase 4 local verification'}}
    if args.verify_replay:
        replay_client, replay_data, replay_hypothesis, replay_report = agents(config, True)
        if (replay_hypothesis != hypothesis or replay_report != report
                or build(commit, replay_data, replay_report) != manifest or sha_outputs() != before):
            raise ValueError('second run did not reproduce identical artifacts')
        verification['runs'].append(stats(replay_client))
        verification['secondRunSha256'] = sha_outputs()
        verification['secondRunUnchanged'] = True
    dump(folder / 'verification.json', verification)
    previous_status = load(folder / 'status.json')
    if previous_status.get('status') != 'COMPLETED':
        dump(folder / 'status.json', {'schemaVersion': '1', 'status': 'COMPLETED',
            'manifestHash': canonical_hash(manifest), 'script_commit': commit,
            'model': report['model'], 'previous_attempt': previous_status,
            'verification': 'data/phase4/verification.json',
            'provenance': {'mode': 'FROZEN', 'source': 'Strict audited Phase 4 completion'}})
    write_docs(report, data, manifest, verification)
    print(json.dumps({'manifestHash': canonical_hash(manifest), 'resultsHash': manifest['resultsHash'],
        'script_commit': commit, 'runs': verification['runs']}, ensure_ascii=True))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
