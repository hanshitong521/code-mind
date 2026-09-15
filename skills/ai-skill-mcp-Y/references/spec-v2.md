# SkillMind Ultimate V2.0 — 开发规范（全文）

> **Skill Runtime Layer for AI Agent**：不是 Skill 文件管理器，而是技能运行层。
> 版本：`2.0.0` ｜ 目标：99 分生产级 AI 技能基础设施
> 上位原则继承 `spec-v1.md`：**能力做大，入口做小；精准触发，按需展开；关键证据永不丢。**

本文件是 SkillMind V2.0 的**唯一规格来源**。所有子任务（schemas / scripts / references / templates / tests）都以此为准；
与 `spec-v1.md` 冲突时，**V2 定平台形态，V1 定审计方法论**，二者互补不互斥。

---

## 0. 定位与边界

| 项 | 内容 |
|---|---|
| 是什么 | Skill 注册 · 动态发现 · 智能路由 · 评分 · 生命周期 · MCP 网关 · Token 分级加载 · 自动验证 · 长期进化 |
| 不是什么 | 不是 Skill 文件管理器；不是第二个 Router（运行时权威路由只有一个，见 §9.4）；不取代 RequirementMind / Brain / TokenMind / TestMind |
| 落位 | `skills/ai-skill-mcp-Y/`（skill_id 保持稳定；产品名 SkillMind；别名触发词 `skillmind`） |
| 宿主 | Cursor / Claude Code / Codex / 本地模型 —— 同一套注册表与路由规则 |

### 0.1 与既有五层栈的关系（禁双开）

```
RequirementMind  → WHAT     做什么（FROZEN 决策）
project-brain    → WHY      为什么 / ADR / 坑
TokenMind        → CTX      读多少 / 从哪读
SkillMind        → HOW-选   选哪个技能 / 用什么链 / 暴露多少工具   ← 本 skill
ai-code/ai-design→ HOW-做   怎么写
TestMind         → VERIFY   真的成了吗
Evidence Gate    → 证据     能不能证明
```

**SkillMind 只做"选"，不做"做"。** 一旦开始写业务码、改生产配置，即越界（V1 §22.6 禁多层 Router）。

---

## 1. 问题分析（为什么需要运行层）

```
Skill 数量 ↑ · MCP Tool 数量 ↑ · Agent 数量 ↑ · 并行 Session ↑
        ↓
误触发 + 重复读 + 重复调用 + Context 污染 + 技能冲突 + 重试风暴
        ↓
Token ↑ / 延迟 ↑ / 成功率 ↓ / 返工 ↑
```

| 症状 | 根因 | SkillMind 对策 |
|---|---|---|
| 不知道选哪个 Skill | 无注册表、无标签、无评分 | §3.1 Registry + §3.2 Router |
| Skill 质量无法评价 | 无指标、无记录 | §3.3 评分引擎 |
| 垃圾 Skill 越积越多 | 无淘汰机制 | §3.4 进化生命周期（**只降级不自动删**） |
| 多 Agent 共享互相污染 | 无隔离、无身份 | §4 MCP 网关（agent/project/session） |
| Token 越用越贵 | 全量常驻 | §5 三级加载 |
| 升级即翻车 | 无回归验证 | §7 TestMind 闭环 |

---

## 2. 核心架构

```
                          AI Agent
                             │
                             ▼
                    ┌─────────────────┐
                    │ SkillMind Router│  ← 运行时唯一权威路由
                    └────────┬────────┘
        ┌───────────┬────────┼────────┬───────────┐
        ▼           ▼        ▼        ▼           ▼
   SkillRegistry TokenMind  Brain  TestMind   (评分/进化)
        │
        ▼
   ┌─────────────┐
   │ MCP Gateway │  agent_id / project_id / session_id / permission / logging
   └──────┬──────┘
          │
   ┌──────┴───────┬────────────┬──────────┐
   ▼              ▼            ▼          ▼
RequirementMind CodeMind   Database   Security
```

**离线 vs 运行时**：Registry/Router/评分/进化是**离线或准实时**的治理动作；运行时只消费其产物（registry.json + 路由结果），不做二次决策。

---

## 3. 四大核心模块

### 3.1 Skill Registry（注册表）

数据结构（每技能一条）：

```yaml
skill_id: ai-code                 # 稳定 id，禁改
name: ai-code
category: backend                 # backend|frontend|data|infra|governance|docs|test
tags: [java, springboot, mapper, sql, bug]
version: 8.0.0
status: verified                  # draft|testing|verified|deprecated|blocked
score: 96                         # 由 §3.3 产出；无记录时 null
owner: ai-programming-docs
load_mode: on-demand              # always|on-demand|deep
risk: low                         # low|medium|high|critical
destructive: false
triggers: {include: [/ai-code], exclude: [log-only]}
```

**状态机**（§3.4 驱动）：

```
draft ──▶ testing ──▶ verified ──▶ deprecated
  │           │            │            │
  └───────────┴────────────┴────────────┴──▶ blocked（安全/合规一票否决）
```

- `blocked` 不可被自动降级覆盖，只能人工解除。
- `deprecated` **不删除**：低频 ≠ 可删（灾备/事故/迁移/安全类 90 天不用仍是 P0）。

### 3.2 Skill Router（核心）

**输入**：用户任务原文、项目类型、复杂度（L0–L3）、风险等级、历史记录。
**输出**：推荐 Skill 列表（带置信度与理由）+ 执行链 + 被排除项与排除理由。

```
用户任务 → Requirement Analysis → Skill Router → Skill Ranking → Skill Chain → Agent 执行
```

路由四级演进（**同一时刻只启用一级，禁并存**）：

| 级 | 方法 | 启用条件 |
|---|---|---|
| 1 | 规则 + 标签 | 默认，零依赖 |
| 2 | Embedding 相似度 | 规则召回不足（Recall < 0.8）且注册表 > 30 条 |
| 3 | LLM Router | 多义任务、跨域任务占比 > 20% |
| 4 | 多专家评分 | 高风险 / 关键路径 |

### 3.3 评分引擎

```
Score = 成功率×40% + 准确率×30% + Token效率×15% + 速度×10% + 稳定性×5%
```

| 分项 | 定义 | 归一化 |
|---|---|---|
| 成功率 | 任务成功 / 总调用 | 直接用 0–1 |
| 准确率 | 无返工 / 无 bug escape | 直接用 0–1 |
| Token 效率 | `baseline_token_avg / token_avg` | `clamp01()`，上限 1.0 |
| 速度 | `baseline_time_avg / time_avg` | `clamp01()`，上限 1.0 |
| 稳定性 | 方差小 / 无 crash | 直接用 0–1 |

**原始记录**（必须与分数同时展示，禁只用分数掩盖事实）：

```json
{"skill_id":"ai-code","metrics":{"success_rate":0.95,"accuracy":0.93,"token_avg":2500,
 "time_avg":15,"stability":0.98,"bug_escape":0.01},"baseline":{"token_avg":3000,"time_avg":20}}
```

分档：`95–100 生产级` / `90–94 强` / `80–89 可用待优化` / `70–79 上线前复查` / `<70 重设计或禁用`。

### 3.4 Skill Evolution（进化生命周期）

```
Skill 创建 → 真实任务运行 → TestMind 验证 → 收集反馈 → 重新评分
        → 优化 Prompt → 发布新版本（旧版 deprecated，不删除）
```

自动治理生命周期（对齐 V1 §19）：

```
DISCOVER → BASELINE → AUDIT → CLASSIFY → CHANGE → TEST → COMPARE → DEPLOY/ROLLBACK → MONITOR
CLASSIFY ∈ {KEEP, OPTIMIZE, MERGE, SPLIT, LAZY-LOAD, DISABLE-CANDIDATE, BLOCK}
```

**红线**：系统可自动产出 `DISABLE-CANDIDATE`，**禁止自动删除** Skill / 自动改安全权限 / 自动改生产 Tool。

---

## 4. MCP Gateway（多 Agent 共享）

必须支持的身份与治理字段：

| 字段 | 作用 | 缺失后果 |
|---|---|---|
| `agent_id` | 区分调用方 Agent | 记忆污染 |
| `project_id` | 区分项目 | 项目串数据 |
| `session_id` | 区分会话 | 上下文串味 |
| `permission` | `read` / `execute` / `admin` | 越权 |
| `logging` | 调用留痕 | 无法审计 |

隔离要求（P0）：

- 同一 MCP 禁止每个 Agent 无脑冷启动 → 共享 daemon；
- 全局可变 task state 禁止；请求必须带 `correlation_id`；
- Queue / Timeout / Retry **均有界**：防 `5 Agent × 3 retry = 15×` 重试风暴；
- 写操作（destructive）显式隔离 + 二次权限检查；
- 失败降级：`检测 → 一次有限重连 → 可降级则降级 → 否则给明确证据，不无限卡住`。

工具分层与暴露预算：

```
Core/Discovery（少量只读） → Domain Tools（按任务域） → Write/Destructive（明确写意图） → Deep/Expensive（默认隐藏）
单任务最小充分集常见 3–8 个，非硬顶
```

---

## 5. 三级加载（TokenMind 集成）

| 级 | 加载内容 | 预算 |
|---|---|---|
| L0 | `name` + 极短 `description` + `tags` + `score` | ≤ 100 tokens |
| L1 | `SKILL.md` 根文档（路由器） | 命中才加载 |
| L2 | `scripts` / `examples` / `references` | 执行时按需单读 |

**目标：减少 ≥50% 无效上下文。** Token 节约优先级不可颠倒：

```
1 不加载 → 2 不重复加载 → 3 不重复调用 → 4 缓存复用 → 5 增量读取 → 6 结构化筛选 → 7 摘要 → 8 深度压缩
```

最省 Token 的内容，是**根本没必要进入上下文**的内容。

---

## 6. 记忆分层（Brain 集成）

| 层 | 内容 | 归属 | 禁 |
|---|---|---|---|
| 个人记忆 | 用户偏好、习惯 | 用户级 | 进 Skill 经验 |
| 项目记忆 | 项目事实、约定、ADR | 项目 Brain | 跨项目共享 |
| Skill 经验 | 该技能的成功模式、坑 | Skill Evolution | 混入个人数据 |
| 公共知识 | 通用最佳实践 | 公共 | 携带项目敏感信息 |

**铁律**：项目数据只能进项目 Memory；通用经验才进 Skill Evolution。Skill **不保存个人污染数据**。
两态：`candidate →（TestMind/Evidence 验证）→ verified →（多次失效/版本漂移）→ stale/deprecated`。

---

## 7. TestMind 闭环（自动验证）

所有 Skill 必须测试，四类：

| 类 | 内容 |
|---|---|
| 功能测试 | Skill 是否真的执行 |
| 回归测试 | 升级是否破坏原有行为 |
| 对抗测试 | 模拟错误/恶意需求 |
| Benchmark | 不同模型效果比较 |

**禁止只报压缩率**。必须同时报：`TaskSuccess · InputTokens · OutputTokens · ToolCalls · DuplicateCalls · Latency · Rework · EvidenceRetention`。

输出 `Skill Score Report`（模板 `templates/skill-score-report.md`）。
上线门槛（对齐 V1 §25）：正确 Gate PASS + Evidence Gate PASS + 安全 Gate PASS + 无新增严重冲突 + trigger 四类测试 + 回滚方式明确 + ≥3 真实任务 A/B。

---

## 8. Skill 开发规范

```
<skill-name>/
├─ README.md          # 人读入口
├─ SKILL.md           # 根路由器（≤120 行）
├─ skill.yaml         # 统一 manifest（§17）
├─ references/        # 深层参考（命中才读）
├─ templates/         # 产出模板
├─ scripts/           # 可执行工具
├─ tests/             # trigger 四类 + 用例
└─ benchmark/         # 基准任务与基线
```

`skill.yaml` 最小字段见 §17；骨架见 `templates/skill-skeleton/`。
**尺寸**：高频常驻根 < 200 words；普通根 < 500 words；> 800 words 强制拆 `references/`。
**禁为拆而拆**：一次任务要读 ≥5 个碎文件 = 失败，合回去。

---

## 9. 智能路由算法（细则）

### 9.1 打分要素

```
route_score(skill, task) =
    0.45 × 标签/关键词命中
  + 0.25 × 触发词命中（triggers.include）
  + 0.15 × 项目类型匹配（category）
  + 0.10 × 历史成功率（score 归一）
  + 0.05 × 上下文成本惩罚（root_lines 越大越扣）
```

**列表级过滤（同量级带）**：入选项的 `route_score` 必须 ≥ **首选 × 0.45**，否则降为 `excluded`
并写明理由。没有这条，会出现两类**弱信号噪声**与首选并列进榜：

| 噪声源 | 实测 | 为什么必须挡 |
|---|---|---|
| 纯 `category` 命中 | 治理任务里 `ai-requirement` 只靠 `category=governance` 拿 0.18 | 同 category 不等于同职责；它没有一条标签/触发词命中 |
| 单个中文二字窗口 | `ai-design` 靠 description 里的「审计」二字拿 0.25 | 通用词命中是偶然，不是相关性 |

0.45 的取值依据：真实需要多技能协同的任务（如 requirement 0.73 + coding 0.61）比值约 0.84，
远高于阈值；被挡掉的都是比值 < 0.45 的噪声项。

### 9.2 硬过滤（先于打分）

- `status ∈ {blocked}` → 永不推荐；
- `status == deprecated` → 仅当无替代时推荐，且标注；
- 风险等级 `critical` 且 `risk == high` 且无人工确认 → 降级为候选并告警；
- `exclude` 命中 → 排除并记录理由。命中判定：单 token / 中文短语按**子串**；多词英文短语（`requirement freeze`）按**内容词全出现（AND）** —— 整句子串匹配对短语过严（任务写成 `freeze requirement` 就漏判，护栏失效）。
- `exclude` 来源：`_common.derive_excludes()` 从 description 的**否定从句**（`Not for …` 之后）派生，与 `skill.yaml: triggers.exclude` 合并。**否定从句不派生 = 精确度无护栏**（历史缺陷：`exclude` 曾恒为 `[]`）。

### 9.3 Skill Chain（执行链）

按任务阶段装配，顺序即执行顺序：

```
requirement → design → coding → verification
```

链只由**注册表里 `phase`/`category` 与任务阶段映射**决定，禁止硬编码具体 skill 名。

### 9.4 唯一权威路由

Brain / TokenMind / SkillMind / MCP **不得各做一套 Router**。运行时权威 = SkillMind Router；
其余层只提供输入信号（Brain 给历史、TokenMind 给预算、MCP 给工具清单）。

---

## 10. 企业级安全

| 域 | 要求 |
|---|---|
| 权限 | `read` / `execute` / `admin` 三级；destructive 工具需 `execute` 且二次确认 |
| 日志 | skill 调用记录、token 消耗、成功率、错误分类 |
| 审计 | 谁调用、何时、哪个项目、产生什么结果 |
| 供应链 | 第三方 Skill/MCP 接入前审计：shell / curl / 动态下载 / secret / `~/.ssh` / cookie / git credential / 文件删除 / DB write / 网络上传 / 配置修改 / prompt injection / 隐藏 telemetry |
| 评级 | `SAFE` / `REVIEW` / `BLOCK`；**高 Star ≠ 可信** |
| 脱敏 | 遥测不保存原始敏感输入 |

---

## 11. 与现有项目整合

| 系统 | 职责 | 交接物 |
|---|---|---|
| RequirementMind | WHAT | `decisions.json` FROZEN → 路由输入（项目类型/复杂度/风险） |
| SkillMind | 选 | `registry.json` + `route-result.json` |
| TokenMind | 读多少 | 路由结果里的 `estimated_tokens` / `load_level` |
| Brain | 记住 | `candidate` 经验 → 验证后 `verified` |
| TestMind | 验证 | `Skill Score Report` |

**本仓控制面打通**（只读消费，禁反向改写）：

| 文件 | 用途 |
|---|---|
| `shared/release-manifest.yaml` | 技能清单 + `content_hash` + `artifact_path` → 注册表 `bundled` 与 `hash` 来源 |
| `shared/capability-registry.yaml` | `capabilities` / `phases` / `tool_budget` → 路由的阶段映射与工具预算 |
| `shared/schema-versions.yaml` | 契约版本注册 → 版本兼容判定 |
| `deploy.bundle.yaml` | 分发清单 → `bundled` 判定 |

**哈希语义必须复用 `_common.hash_tree`**（与 `scripts/_release_lib.py` 逐字节等价），否则产生假 DRIFT。

---

## 12. 开发路线

| Phase | 内容 | 目标分 |
|---|---|---|
| P0 基础 | Registry + MCP 接口 + Skill 加载 | 80 |
| P1 智能 | Router + Score Engine + Token 优化 | 90 |
| P2 企业 | Gateway + Multi-Agent + Permission + Audit | 95 |
| P3 Ultimate | 自动进化 + Benchmark + AI 评审 + 自我优化 | 99 |

---

## 13. 验收标准

**技术指标**

| 指标 | 目标 |
|---|---|
| Skill 加载时间 | < 100 ms |
| Token 减少 | 30%–60% |
| Router 准确率 | > 90% |
| 多 Agent 隔离 | 100% |

**质量指标**：Skill 自动评分 · 自动测试 · 自动升级（受 §3.4 红线约束）。

---

## 14. 接口契约（**强制**，所有脚本必须实现）

> 这是并行子任务的公共接口。改接口 = 改本文件 + 同步所有消费方，禁止私改。

### 14.1 统一 CLI

```bash
python3 scripts/skillmind.py registry build  [--root R] [--out P] [--json]
python3 scripts/skillmind.py registry query  [--tag T] [--status S] [--category C] [--min-score N] [--json]
python3 scripts/skillmind.py route           --task "..." [--project-type T] [--risk R] [--complexity L0..L3] [--top N] [--json]
python3 scripts/skillmind.py score record    --skill-id ID --metrics-json '<json>' [--baseline-json '<json>'] [--store P]
python3 scripts/skillmind.py score report    [--skill-id ID] [--store P] [--json]
python3 scripts/skillmind.py telemetry append --event-json '<json>' [--store P]
python3 scripts/skillmind.py telemetry summary [--store P] [--json]
python3 scripts/skillmind.py manifest validate [--path P] [--json]
python3 scripts/skillmind.py verify          [--root R] [--installed D] [--json]
python3 scripts/skillmind.py selftest        [--json]
```

子脚本必须**可独立运行**（同名参数），`skillmind.py` 只做调度：

```
scripts/registry_build.py    --root R [--out P] [--json]
scripts/router.py            --registry P --task "..." [--project-type T] [--risk R] [--complexity Lx] [--top N] [--json]
scripts/score.py             record|report [...]
scripts/telemetry.py         append|summary [...]
scripts/manifest_validate.py --path P [--json]
scripts/selftest.py          [--json]
```

**退出码**：`0` = 通过；`1` = 校验失败 / 存在 DRIFT；`2` = 用法或环境错误。
**状态目录**：默认 `<repo_root>/.skillmind/`（`registry.json` / `scores.json` / `telemetry.jsonl`）。

### 14.2 registry.json

```json
{
  "schema_name": "skillmind-registry", "schema_version": 1,
  "generated_at": "ISO8601", "root": "/abs",
  "sources": ["shared/release-manifest.yaml", "..."],
  "skills": [{
    "skill_id": "ai-code", "name": "ai-code", "path": "skills/ai-code/SKILL.md",
    "dir": "skills/ai-code", "description": "...", "category": "backend",
    "tags": ["java"], "version": "8.0.0", "status": "verified", "score": null,
    "owner": "ai-programming-docs", "load_mode": "on-demand", "risk": "low",
    "destructive": false, "always_apply": false, "root_lines": 52, "root_words": 380,
    "refs": ["references/lean.md"], "triggers": {"include": [], "exclude": []},
    "bundled": true, "hash": "sha256:...", "source": "release-manifest|filesystem"
  }],
  "rules":  [{"path": ".cursor/rules/x.mdc", "always_apply": true, "lines": 12}],
  "mcps":   [{"name": "x", "tools": 0, "standing": false}],
  "overlap":[{"a": "x", "b": "y", "shared_tags": ["t"], "severity": "warn"}],
  "stats":  {"skills": 6, "verified": 1, "always_apply_rules": 0, "bundled": 4}
}
```

### 14.3 route-result.json

```json
{
  "schema_name": "skillmind-route-result", "schema_version": 1,
  "task": "...", "method": "rule+tag", "confidence": 0.88,
  "recommended": [{"skill_id": "ai-code", "confidence": 0.92, "reasons": ["tag:java", "trigger:/ai-code"]}],
  "chain": [{"order": 1, "phase": "coding", "skill_id": "ai-code", "why": "..."}],
  "excluded": [{"skill_id": "ai-concise", "reason": "status=deprecated 且已有替代"}],
  "warnings": []
}
```

### 14.4 score-record.json

```json
{
  "schema_name": "skillmind-score-record", "schema_version": 1,
  "skill_id": "ai-code", "recorded_at": "ISO8601",
  "metrics": {"success_rate": 0.95, "accuracy": 0.93, "token_avg": 2500,
              "time_avg": 15, "stability": 0.98, "bug_escape": 0.01},
  "baseline": {"token_avg": 3000, "time_avg": 20},
  "subscores": {"success_rate": 95.0, "accuracy": 93.0, "token_efficiency": 100.0,
                "speed": 100.0, "stability": 98.0},
  "weights": {"success_rate": 0.40, "accuracy": 0.30, "token_efficiency": 0.15,
              "speed": 0.10, "stability": 0.05},
  "score": 95.8, "grade": "Production Grade"
}
```

默认基线（未提供时）：`token_avg = 3000`、`time_avg = 20`，并在输出中标注 `baseline_defaulted: true`。
（上式手算：`0.40×0.95 + 0.30×0.93 + 0.15×1.0 + 0.10×1.0 + 0.05×0.98 = 0.958`。）

### 14.5 telemetry-event（§23 字段）

```json
{"schema_name": "skillmind-telemetry-event", "schema_version": 1,
 "ts": "ISO8601", "session_id": "", "agent_id": "", "project_id": "", "task_id": "",
 "skill_id": "", "tool_id": "", "triggered": true, "trigger_reason": "",
 "context_tokens_loaded": 0, "result_tokens": 0, "call_count": 0, "cache_hit": false,
 "latency_ms": 0, "success": true, "rework": 0, "p0_evidence_retained": true,
 "error_class": null, "correlation_id": ""}
```

---

## 15. 反模式（继承 V1 §22，违反即 FAIL）

| 反模式 | 为什么错 |
|---|---|
| 万能 Skill | 什么都触发 = 始终常驻 |
| description 写满工作流 | Agent 只读 description 不读正文 |
| 根 SKILL.md 塞尽参考资料 | 破坏渐进式披露 |
| 一次暴露全部 tool | 后台能力强 ≠ 前台全展示 |
| 只看压缩率 | 最危险；删了错误证据直接 FAIL |
| 多层都做 Router | 冲突 + 重复决策 |
| 每个任务跑全部测试 | 测试范围应与风险/影响匹配 |
| 自动删除低频 Skill | 灾备/事故/迁移类 90 天不用仍是 P0 |
| 分数掩盖原始指标 | 禁止 |

---

## 16. Definition of Done（V2.0）

- [ ] Registry 可机械生成（`registry build`），并消费本仓控制面
- [ ] Router 可解释（每条推荐带 reasons），硬过滤先于打分
- [ ] 评分引擎可复现（同输入同输出），原始指标与分数同时输出
- [ ] MCP 网关身份/隔离/重试边界写清，且有可校验的遥测事件结构
- [ ] 三级加载有明确预算与落点
- [ ] 四层记忆边界写清，项目数据禁入 Skill 经验
- [ ] TestMind 四类测试 + Score Report 模板
- [ ] 供应链审计评级 SAFE/REVIEW/BLOCK
- [ ] Hard Gate + Evidence Gate + 回滚方式
- [ ] 全部脚本可在**裸 Python 3.9+（无第三方依赖）**下运行
- [ ] `selftest` 全绿；不破坏本仓 `validate_bundle.py` / `verify_skill_drift.py` 既有基线
- [ ] 哈希语义与 `scripts/_release_lib.py` 逐字节一致（禁假 DRIFT）

---

## 17. 统一元数据协议（skill.yaml）

机读契约：`schemas/skill-manifest.schema.json` ｜ 校验：`scripts/manifest_validate.py` ｜ 骨架：`templates/skill-skeleton/skill.yaml`

```yaml
id: <skill-id>            # 稳定 skill_id，与目录名一致，禁改
name: <display-name>      # 产品名，可与 id 不同
version: <major.minor.patch>
kind: skill               # skill|mcp|tool|rule（预留给统一登记）
owner: <capability-owner> # 对齐 shared/capability-registry.yaml 的 exclusive_owners
description: >-           # 只答「何时用 / 何时不用」，禁写完整工作流
category: <backend|frontend|data|infra|governance|docs|test>
tags: []
triggers: {include: [], exclude: []}
cost:   {context_tokens_estimate: 0, runtime_class: cheap|standard|expensive}
risk:   {level: low|medium|high|critical, destructive: false}
loading:      {mode: always|on-demand|deep}
verification: {required: true}
security_permissions: [read]
extensions:   {}          # §17 扩展自由区
```

**与 spec-v1 §17 的差异（V2 生效）**：

| 字段 | V1 | V2 | 原因 |
|---|---|---|---|
| `cost.runtime_class` | `low\|medium\|high` | `cheap\|standard\|expensive` | 描述的是**开销档**而非等级，避免与 `risk.level` 同词不同义 |
| `kind` | 四值平铺 | 四值保留，本契约主用于 `skill` | 保持前向兼容 |
| 扩展字段 | 顶层平铺 | 收进 `extensions` | 顶层 `additionalProperties: false` 才能挡住字段漂移 |

**设计取舍**：不要一次把 manifest 做成 100 字段平台。只登记**真正参与路由、预算、审计**的字段；
其余一律进 `extensions`，避免每加一个字段就升 schema 版本。
