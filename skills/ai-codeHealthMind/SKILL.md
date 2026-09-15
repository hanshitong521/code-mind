---
name: ai-codeHealthMind
version: 1.0.0
description: >-
  CodeHealthMind — AI 写完代码后的强制代码健康 Gate。审 diff/commit/range/repo，
  找出死代码·重复·错误抽象·过度设计·复杂度·错误处理·并发·资源·DB·性能·可测试性退化，
  分级（CRITICAL/HIGH/MEDIUM/LOW）→ 证据校验 → 评分 → PASS/WARN/BLOCK/UNKNOWN。
  Triggers: /codehealth, /ai-codeHealthMind, CodeHealthMind, 代码健康, 垃圾代码,
  死代码, 过度设计, 合并准入, 代码质量门.
disable-model-invocation: true
---
encoding:../../shared/core.md
trig:/codehealth|CodeHealthMind|代码健康|垃圾代码|合并准入 prio:rules>this load:本页 其余docs/命中单读 禁批读
axiom:证据优先>删除优先>最小修改; AI≠证据; 不同上下文复审; 高风险跨模型复核; 修复后必重跑 Gate; 工具失败不假绿
ssot:docs/architecture.md schema:docs/finding-schema.md risk:docs/risk-model.md

Goal: 用最少 Token、最可靠证据，阻止 AI 把长期维护成本悄悄带进生产代码。
Not: 不做需求澄清(→ai-requirement); 不做完整测试策略(→TestMind); 不替代 SAST/编译器; 不大规模重写业务。

# 执行入口（唯一）

```
python codehealth.py <command> [flags]        # 零依赖，无需 PYTHONPATH
```
需要 Python ≥3.10。本机若托管解释器损坏，用 `D:\APJ\Anaconda\python.exe`。

## 命令
| 命令 | 用途 |
|---|---|
| `review` | 跑 Gate，出报告 |
| `fix` | 出修复计划；`--apply` 才动代码（只动可证安全的） |
| `verify` | 修复后重跑 Gate 并与上一轮对比（规范 §34 强制） |
| `explain CHM-000123` | 解释单条 finding 的完整证据链 |
| `baseline --show\|--update` | 查看/刷新基线（历史债不阻断，新增债才阻断） |
| `probe` | 真实探测工具链可用性与版本 |
| `init` | 写 `.codehealth.yml` |

## 目标选择（6 选 1，默认 diff）
```
--diff | --staged | --commit <sha> | --range <a>..<b> | --file <path> | --repo
```

## 输出
```
--format console|json|markdown|sarif   -o <file>
```
退出码固定：`0` PASS/WARN · `1` BLOCK · `2` 工具或配置错误 · `3` UNKNOWN

# 12 步工作流（规范 §25）

```
1  Resolve target        → gitctx.resolve_context
2  Load requirement      → --requirement <file>（已过 secret 过滤）
3  Collect diff          → changed files + hunks
4  Deterministic layer   → native-java/native-vue + javac/PMD/CPD/SpotBugs/Semgrep/Knip
5  Minimal context       → packer.build_context_pack（按风险扩张，默认只审 diff）
6  Semantic reviewer     → riskrouter 决定 1~2 个 reviewer + persona
7  Normalize findings    → 稳定 id、分类、修复路由
8  Validate high risk    → evidencevalidator（RV-001..003、动态入口、severity 打假）
9  Dedup + baseline      → 同问题多来源合并；历史债 vs 新增债
10 Score + Gate          → 10 维评分 + 硬门槛 + PASS/WARN/BLOCK/UNKNOWN
11 Repair routing        → SAFE_AUTO_FIX / WRITER_FIX / MANUAL_DECISION
12 Re-run gate           → codehealth verify（修复后必须重新证明）
```

# 硬规则

- **证据优先**：HIGH/CRITICAL 必须带 deterministic 证据；只有语义推断一律降 MEDIUM。
- **AI ≠ 证据**：LLM 只能说「疑似」，不能证明死代码/性能/并发。
- **删除优先**：先删、再用标准库、再用项目已有能力、最后才加抽象。
- **错误抽象 > 重复**：出现重复**不得自动抽象**；先答 7 问（同语义？同变化原因？同生命周期？已有模式？≥3 次？降低成本？引入更多泛型？）。
- **上下文隔离**：Reviewer 绝不接收 Writer 的自我解释。默认 A 模式。
- **不随机表决**：两个 Reviewer 冲突 → Evidence Validator 裁决。
- **动态入口安全**：反射/IOC/SPI/MQ/XML/RPC/动态 import 任一命中 → 禁止自动删除。
- **失败降级**：工具缺失 → `TOOL_DEGRADED`；若 HIGH/CRITICAL 取证依赖该工具 → `UNKNOWN`（**禁止 PASS**）。
- **语言无覆盖 ≠ 通过**：变更全是无 provider 覆盖的语言（Python/Go/Rust/…）→ `UNKNOWN`(3)，不是 PASS。
- **修复后必须重跑**：`codehealth verify`。

# 判据速查

| 场景 | 结论 |
|---|---|
| compile fail / test fail | BLOCK |
| CRITICAL（未 accepted_risk） | BLOCK |
| HIGH（未 accepted_risk） | BLOCK |
| 新增 MEDIUM > `gates.max_new_medium` | BLOCK |
| 新增 MEDIUM ≤ 阈值 | WARN |
| 只有 LOW | PASS |
| 工具降级、无证据缺口 | WARN |
| 工具降级、且影响 HIGH/CRITICAL 取证 | **UNKNOWN** |

# 配置

`.codehealth.yml`（`codehealth init` 生成；模板见 `.codehealth.example.yml`）。
严格校验：未知 key / 类型错误 → 硬失败，不静默取默认值。

关键旋钮：
- `tools.*.enabled` — 关掉某个 provider
- `tools.<t>.home` / `.bin` — 或环境变量 `CHM_PMD_HOME` / `CHM_SPOTBUGS_HOME` / `CHM_SEMGREP_BIN` / `CHM_KNIP_BIN` / `CHM_JAVA_HOME`
- `review.backend` — `off` \| `rule`（确定性本地启发式，报告中如实标注）\| `llm`（`llm_command` 必须配置，否则报 CONFIG 错误，**不偷偷降级**）
- `gates.*` — 阻断阈值
- `dead_code.allow_auto_delete` — 默认 `false`；即使为 `true`，也只改「未用 import / debug 残留」这类可证机械项
- `accepted_risks` — 带 `expires`，**过期即重新阻断**

# 目录

```
codehealth.py          # 入口
src/chm/               # 引擎（纯标准库，ADR-001）
  schema.py            # Finding 标准模型（规范 §8）
  contracts.py         # ScanContext / ProviderResult / EvidenceProvider
  core/                # orchestrator·riskrouter·score·gate·baseline·dedup·validator
  context/             # git·symbols·packer·secretfilter
  adapters/            # 真实 CLI 适配器
  analyzers/           # 内建确定性分析器（Java / Vue）
  reviewers/           # 5 个 persona + 隔离 runtime
  reports/             # console·json·markdown·sarif
rules/                 # PMD 规则集（已验证）+ Semgrep 规则
docs/                  # 架构·schema·风险模型·规则编写·ADR
test/                  # fixtures·golden·adversarial·benchmark
```

# 失败时怎么读

1. `codehealth probe` → 哪些工具真的可用、什么版本
2. 报告里的 `tools[]` → 每个 provider 的真实命令、耗时、状态
3. `tool_errors[]` → `kind` 是 `MISSING`/`TIMEOUT`/`NONZERO_EXIT`/`MALFORMED_OUTPUT`/`PARTIAL_OUTPUT`
4. `evidence_gap=true` → 有结论因缺证据而无法成立；此时 Gate 只能是 WARN/UNKNOWN，不会是 PASS

# 与上下游

```
ai-requirement → Writer → CodeHealthMind PRE-GATE → TestMind → CodeHealthMind POST-GATE → Merge
```
PRE-GATE：结构·复杂度·死代码·重复·明显 bug·过度设计。
POST-GATE：测试证据·回归·修复引入的新债·最终 delta。
