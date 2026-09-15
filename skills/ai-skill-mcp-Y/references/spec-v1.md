# Skill / MCP Governance Ultimate — 99 分开发规范 V1

> 核心原则：**Build Big, Load Small, Trigger Precisely, Expand on Demand, Preserve Evidence.**  
> 中文：**能力做大，入口做小；精准触发，按需展开；最大限度节约 Token，但关键证据永不丢。**

---

## 0. 文档定位

本文定义一套面向多 Agent 的 Skill / MCP / 项目指令治理体系。目标不是继续堆更多 Skill，而是让未来即使存在几十到上百个 Skill、几十个 MCP Server、数百个 Tool，单个任务仍只暴露**最小充分能力与最小充分上下文**。

本规范适配你现有的整体职责边界：

```text
RequirementMind  → What should be done?
Project Brain     → What should the Agent know?
TokenMind         → What should the Agent see, how much, and when?
Skills / MCP      → What can the Agent do, and how?
TestMind          → Did it really work?
Evidence Gate     → Can it prove the result?
```

治理层不取代任何一层。它负责**发现浪费、冲突、误触发、重复、过度暴露和风险，并给出可验证的优化方案**。

---

# 1. 为什么现在必须做治理层

当 Skill / MCP 数量小时，很多问题不明显：

- 多读 1 个 Skill，只多几百 Token；
- 多暴露 10 个 Tool，模型仍能选对；
- 两个 Skill 职责重叠，也许只是多做一步；
- MCP 每次冷启动，单 Agent 还能忍受。

规模上来以后会出现乘法放大：

```text
Skill 数量 ↑
MCP Tool 数量 ↑
Agent 数量 ↑
并行 Session ↑
项目规则 ↑
长期记忆 ↑
日志/搜索结果 ↑
        ↓
误触发 + 重复读 + 重复调用 + Context 污染 + 冲突 + 重试风暴
        ↓
Token ↑ / 延迟 ↑ / 成功率 ↓ / 返工 ↑
```

因此后续优化目标不是“Skill 越短越好”，而是：

> **总能力可以无限增长，但每个任务实际支付的上下文和调用成本尽可能接近这个任务真正需要的最小值。**

---

# 2. 总目标与优先级

优先级不可颠倒：

1. **正确率 / 任务成功率**
2. **关键证据完整性**
3. **安全边界**
4. **Token / Context 成本**
5. **Tool Call 数量**
6. **延迟**
7. **维护复杂度**
8. **扩展性**

任何优化若出现以下任一情况，直接判定 FAIL：

- 丢失关键报错、异常类型、失败断言、关键行号、SQL 状态等 P0 Evidence；
- 任务成功率明显下降；
- 安全权限被无意扩大；
- 为省 Token 导致 Agent 需要更多返工；
- 工具压缩率很好，但总体任务 Token / 时间更高；
- Skill 不误触发了，但本该触发时也找不到。

---

# 3. 非目标

治理系统 **不做**：

- 不替代 RequirementMind 进行需求决策；
- 不把 Project Brain 变成 Runtime Router；
- 不把 TokenMind 变成 Workflow Orchestrator；
- 不把 TestMind 变成 Coding Agent；
- 不做“一个万能 Skill 处理全部任务”；
- 不为了评分自动删除低频高价值 Skill；
- 不追求单一“压缩率”漂亮数字。

---

# 4. 总体架构

```text
                           ┌─────────────────────┐
                           │      User Task      │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │   RequirementMind   │
                           │ intent/scope/DoD/risk│
                           └──────────┬──────────┘
                                      │
                                      ▼
                 ┌─────────────────────────────────────────┐
                 │          Governance / Discovery         │
                 │ Skill Doctor / MCP Doctor / Rules Doctor│
                 └──────────────┬──────────────────────────┘
                                │ candidate domains/tools
                       ┌────────┴────────┐
                       ▼                 ▼
               ┌──────────────┐   ┌──────────────┐
               │Project Brain │   │  TokenMind   │
               │knowledge/mem │   │budget/policy │
               └──────┬───────┘   └──────┬───────┘
                      └──────────┬────────┘
                                 ▼
                       ┌─────────────────┐
                       │ Coding / Agent  │
                       │ selected skills │
                       │ selected tools  │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │    TestMind     │
                       │ real verification│
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │ Evidence Gate   │
                       └────────┬────────┘
                                ▼
                       verified feedback
```

关键点：**治理层主要负责离线/准实时审计与策略建议，运行时路由只保留一个权威实现。**

---

# 5. 四个治理能力

## 5.1 Skill Doctor — P0

职责：

- Trigger 是否精准；
- Description 是否过宽；
- Skill 是否与其他 Skill 重叠；
- 根 `SKILL.md` 是否过大；
- 是否适合渐进式披露；
- 是否重复 `AGENTS.md` / Brain 内容；
- 是否把机械规则错误写成自然语言；
- 是否用过多 MUST/ALWAYS/NEVER 约束强模型；
- 是否定义清楚“不该什么时候用”；
- 是否有真实 Trigger 测试。

输出状态：

```text
KEEP
OPTIMIZE
MERGE
SPLIT
LAZY-LOAD
DISABLE-CANDIDATE
BLOCK
```

## 5.2 MCP Doctor — P0

职责：

- MCP Server 生命周期；
- 多 Agent 是否重复启动；
- Tool Schema Token 成本；
- Tool 暴露数量；
- Tool 描述是否混淆；
- 重复/近重复 Tool；
- Tool 错选、重复调用、Retry Storm；
- Result 是否过大；
- Cache / Dedup 是否生效；
- 并发、Session 隔离、Correlation ID；
- destructive tool / secrets / network 权限。

## 5.3 AGENTS / Rules Doctor — P0

职责：

审计：

- `AGENTS.md`
- `CLAUDE.md`
- Cursor Rules
- 项目 System Prompt
- repo instructions
- Skill 常驻规则

主要查：

- 每次都强制读文档；
- 全仓扫描；
- 每次都跑全测试；
- 泛化的“写好代码”等低信息指令；
- 不必要的人为审批 Gate；
- 模型升级后已不需要的脚手架；
- 多层指令冲突。

## 5.4 Definition of Done Generator — P1

不建议一开始独立做巨大 Skill。优先作为 RequirementMind 输出能力或 Governance 子能力。

核心变化：

```text
旧：告诉模型每一步怎么走
新：告诉模型目标、边界、完成条件、必须保留的证据
```

让强模型自己选择路径，治理层只约束结果。

---

# 6. Skill 目录标准

推荐统一：

```text
<skill-name>/
├─ SKILL.md
├─ references/
│  ├─ topic-a.md
│  ├─ topic-b.md
│  └─ ...
├─ templates/
├─ scripts/
└─ tests/
```

## 6.1 根 SKILL.md 只允许放

- Frontmatter；
- 核心原则；
- 精准 When to use / When not to use；
- 路由表；
- 不可破坏的 Invariants；
- 最小 Output Contract。

## 6.2 根 SKILL.md 不应该放

- 600 行 API 文档；
- 所有场景的详细步骤；
- 大量重复示例；
- 可由脚本完成的机械检查；
- 项目专属业务规则；
- 其他 Skill 已经拥有的通用流程。

## 6.3 目标尺寸

不是绝对硬限制，但建议：

- 高频常驻入口：尽可能 <200 words；
- 普通 Root Skill：优先 <500 words；
- 超过约 500–800 words：强制审视能否拆 references；
- 超过 100 行的纯参考资料：默认考虑移出根 Skill。

**注意：不是为了数字而切文件。** 如果拆分导致 Agent 每次多读 5 个碎文件，反而失败。

---

# 7. Trigger 设计规范

## 7.1 Description 只回答一个问题

> “这个任务现在是否应该加载我？”

不要在 description 里总结整个 Skill 工作流。

### 错误

```yaml
description: Use for database work; inspect schema, write migrations, run tests, verify deployment and review SQL.
```

问题：数据库相关任务都可能误触发，而且模型可能只照 description 做而不读正文。

### 推荐

```yaml
description: Use when creating, modifying, or reviewing PostgreSQL schema migrations.
```

## 7.2 Trigger 必须有 4 类测试

1. Positive：必须触发；
2. Negative：明确不能触发；
3. Boundary：模糊边界；
4. Conflict：多个 Skill 都可能触发。

建议附加：

5. Strong-model：检查 Skill 是否过度约束强模型；
6. Weak-model：必要时检查较弱模型是否仍能正确执行。

## 7.3 核心指标

```text
Trigger Precision = Correct Trigger / All Trigger
Trigger Recall    = Correct Trigger / All Needed
Misfire Rate      = Wrong Trigger / All Opportunities
```

不能只追求 Precision；如果 Recall 掉太多，本该用时找不到 Skill 也失败。

---

# 8. Progressive Disclosure（渐进式披露）

理想行为：

```text
Task
 ↓
读取 Skill 名称 + 极短 Description
 ↓
确认相关
 ↓
读取根 SKILL.md
 ↓
根据任务只读取 1~N 个必要 reference
 ↓
执行
```

而不是：

```text
Task
 ↓
读取全部 Skill 正文
 ↓
读取全部 reference
 ↓
上下文先爆一遍
```

## 8.1 三层加载

### L0 — 常驻最小信息

- Skill name；
- short description；
- 极少量项目级强约束。

### L1 — 任务域路由

- 当前 Skill 根文档；
- 当前任务所属领域。

### L2 — 深层参考

只有确实需要时读取：

- heavy docs；
- API refs；
- 安全规范；
- 特定测试流程；
- Deep analysis。

---

# 9. MCP 大能力、小暴露

MCP 后端可以有 100 个 Tool，但单任务不应该默认看到 100 个完整 Tool Schema。

目标：

```text
Full Capability Catalog
         ↓
Domain Discovery
         ↓
Task-relevant tool subset
         ↓
3~8 tools actually exposed when possible
```

这不是硬编码“最多 8 个”，而是**最小充分工具集**原则。

## 9.1 Tool 分层

建议：

```text
Core / Discovery
Domain Tools
Write / Destructive Tools
Deep / Expensive Tools
```

- Core：少量常用只读能力；
- Domain：按任务域暴露；
- Write：按明确写意图暴露或二次权限检查；
- Deep：成本高，默认隐藏。

## 9.2 Tool Schema 优化

审计：

- 冗长 description；
- 重复枚举解释；
- 过宽参数；
- 不清晰返回结构；
- 一个 tool 同时做 5 件事；
- 多个 tool 几乎同义。

原则：

> Schema 不是越短越好，而是让模型用最少推理成本选对工具、构造对参数。

---

# 10. TokenMind 对接

TokenMind 作为运行时 Context OS，负责：

- budget；
- output level；
- dedup；
- incremental read；
- cache；
- repeated-search guard；
- tool-result gate；
- evidence preservation；
- telemetry。

治理层向 TokenMind 提供：

```json
{
  "resource": "skill-or-tool-id",
  "domain": "database-migration",
  "estimated_tokens": 420,
  "priority": "P1",
  "relevance": 0.92,
  "p0_evidence": false,
  "lazy": true,
  "cache_key": "..."
}
```

TokenMind 不应该重新决定 Skill 的业务职责，而是依据统一 metadata 做运行时预算与 Context 策略。

---

# 11. Project Brain 对接

Brain 负责：

- 项目长期规则；
- 验证过的经验；
- 项目事实；
- 知识文档；
- 历史结果。

## 11.1 不进入 Brain 的内容

- 未验证的单次猜测；
- 所有日志全文；
- Skill 流程正文副本；
- Tool Schema 副本；
- 短生命周期临时状态。

## 11.2 Candidate → Verified

建议两态或多态：

```text
candidate
  ↓ TestMind/Evidence 验证
verified
  ↓ 多次失效/版本漂移
stale / deprecated
```

避免错误经验长期污染多 Agent。

---

# 12. TestMind 对接：必须验证“省了以后仍然正确”

不要只测：

```text
Before: 10000 tokens
After:   2000 tokens
Savings: 80%
```

必须至少同时测：

```text
TaskSuccess
InputTokens
OutputTokens
ToolCalls
DuplicateCalls
Latency
Rework
EvidenceRetention
```

## 12.1 E2E A/B

同一组真实任务：

- A：治理前；
- B：治理后；

使用相同模型、相同仓库版本、尽量相同环境。

### 至少覆盖

- 小修改；
- 普通 Feature；
- Debug；
- 数据库任务；
- 跨模块任务；
- 测试修复；
- 一个高风险/大量日志任务。

## 12.2 成功任务成本

建议保留一个综合指标，但不隐藏原始数据：

```text
Successful Task Cost =
Tokens + Tool Calls + Latency + Rework + Error Cost
```

实际计算时先正规化各维度，避免单位不可比。

---

# 13. Evidence Gate

## 13.1 P0 Evidence 示例

- AssertionError；
- Exception 类型；
- failing file/line；
- SQLState / DB error code；
- requestId / traceId；
- 安全权限结果；
- acceptance criteria；
- 关键返回码；
- 决策所依据的最小事实。

## 13.2 可压缩内容

- 1000 条重复成功日志；
- 大量无变化记录；
- 同一 stack trace 重复 N 次；
- 无任务相关性的 metadata；
- 可由引用重新获取的大文本。

## 13.3 规则

```text
最高压缩率 ≠ 最佳系统。
```

如果压缩 98% 但把错误证据删了，评分直接 FAIL。

---

# 14. Instruction / AGENTS.md 治理

## 14.1 从“必读清单”升级为“导航地图”

旧：

```text
每次修改前阅读 architecture.md、database.md、deployment.md。
```

新：

```text
服务边界变化 → architecture.md
Schema 变化   → database.md
准备部署      → deployment.md
否则不默认加载。
```

## 14.2 删除低信息规则

例如：

```text
写高质量代码
认真思考
检查代码
注意性能
使用好命名
```

若没有项目特异性，价值非常低。

## 14.3 保留模型无法猜到的事实

例如：

```text
Vue 2 + Element UI
项目自己的 API 约定
特定 MyBatis 复用约定
业务核算公式
生产禁止写规则
特定目录是配置真源
```

## 14.4 从 Process Control 到 Outcome Control

旧：18 步固定流程。

新：

```text
Goal
Constraints
Definition of Done
Evidence Required
```

只有安全关键、顺序依赖或模型反复失败的步骤才保留为强制流程。

---

# 15. 多 Agent 共享 MCP 要求

P0：

- 同一 MCP 不应被每个 Agent 无脑冷启动；
- 支持稳定共享 daemon 的，应共享；
- Session/Agent ID 隔离；
- 请求有 correlation id；
- 避免全局可变 task state；
- Tool 写操作明确隔离；
- Queue 有界；
- Timeout 有界；
- Retry 有界；
- 防止 5 Agent × 3 retry = 15 倍重试风暴；
- server crash 有最小降级策略；
- telemetry 区分 agent/session/tool。

## 15.1 Runtime Fail-safe

```text
MCP unavailable
  ↓
快速检测
  ↓
一次有限恢复/重连
  ↓
可安全降级则降级
  ↓
不可降级则给明确证据，不无限卡住
```

---

# 16. Skill / MCP 供应链安全

第三方 Skill/MCP 接入前必须审计：

- shell；
- curl/wget；
- 动态下载安装；
- secret/env；
- ~/.ssh；
- browser cookie；
- git credential；
- 文件删除/移动；
- DB write；
- 网络上传；
- 配置修改；
- prompt injection；
- 隐藏 telemetry。

评级：

```text
SAFE
REVIEW
BLOCK
```

不要因为 GitHub Star 高就自动信任。

---

# 17. 统一元数据协议

后续可以逐步加入统一 Manifest，但不要求第一天全部改造。

建议最小字段：

```yaml
id: skill-id
kind: skill|mcp|tool|rule
owner: capability-domain
triggers:
  include: []
  exclude: []
cost:
  context_tokens_estimate: 0
  runtime_class: low|medium|high
risk:
  level: low|medium|high|critical
  destructive: false
loading:
  mode: always|on-demand|deep
verification:
  required: true
```

扩展字段：

```yaml
version:
dependencies:
conflicts:
supersedes:
security_permissions:
cacheability:
freshness:
p0_evidence_policy:
```

不要一次把 Manifest 做成 100 字段平台；先从真正能用于路由、预算、审计的字段开始。

---

# 18. 评分体系（100 分）

前提：Hard Gate 必须 PASS。

| 维度 | 权重 |
|---|---:|
| Task / Behavior Correctness | 20 |
| Trigger Precision | 12 |
| Trigger Recall | 8 |
| Context Efficiency | 12 |
| Tool Efficiency | 10 |
| Evidence Retention | 10 |
| Conflict / Overlap Control | 8 |
| Latency / Runtime | 7 |
| Security / Permission Fit | 7 |
| Maintainability / Clarity | 6 |
| **总计** | **100** |

推荐解释：

```text
95–100  Production Grade / Excellent
90–94   Strong
80–89   Useful but targeted optimization needed
70–79   Review before broad rollout
<70     Redesign / disable candidate / block by risk
```

**禁止用评分掩盖事实。** 必须同时展示原始指标。

---

# 19. 自动治理生命周期

```text
DISCOVER
  ↓
BASELINE
  ↓
AUDIT
  ↓
CLASSIFY
  ├─ KEEP
  ├─ OPTIMIZE
  ├─ MERGE
  ├─ SPLIT
  ├─ LAZY-LOAD
  ├─ DISABLE-CANDIDATE
  └─ BLOCK
  ↓
CHANGE
  ↓
TEST
  ↓
COMPARE
  ↓
DEPLOY / ROLLBACK
  ↓
MONITOR
```

## 19.1 禁止自动删除

系统可以自动提出：

```text
DISABLE-CANDIDATE
```

但低频 Skill 不代表没价值。

例如：

- 灾难恢复；
- 生产事故处理；
- 安全事件；
- 大版本迁移。

这些 90 天不用仍可能是 P0。

---

# 20. Token 节约策略优先顺序

不要一上来做文本压缩。

优先级：

```text
1. 不加载
2. 不重复加载
3. 不重复调用
4. 缓存复用
5. 增量读取
6. 结构化筛选
7. 摘要/压缩
8. 深度压缩
```

原因：

> **最省 Token 的内容，是根本没有必要进入上下文的内容。**

这也是整个治理体系的核心。

---

# 21. 典型真实场景

## 场景 A：改一个 MyBatis SQL

错误：

```text
加载 Java Skill
加载 Spring Skill
加载 DB Skill
加载 Migration Skill
加载全部 AGENTS docs
暴露 80 个 MCP tools
```

正确：

```text
项目最小规则
+ MyBatis 相关 Skill/reference
+ 当前 Mapper/XML
+ 必要 DB read tool
+ 受影响测试
```

## 场景 B：数据库 Schema Migration

应额外展开：

- migration-specific Skill；
- schema docs；
- migration validation tool；
- rollback / production safety；
- TestMind migration cases。

## 场景 C：大日志 Debug

不把 10MB 日志直接塞模型：

```text
Tool 预处理
→ Preserve P0 Evidence
→ 聚类重复错误
→ 上下文只发关键片段
→ Agent 如需再增量展开
```

---

# 22. 反模式

## 22.1 万能 Skill

```text
coding-master-skill
```

什么都触发，结果等于始终常驻。

## 22.2 Description 写完整工作流

Agent 可能只读 Description，不读正文。

## 22.3 为了少文件把所有内容塞根 Skill

破坏 Progressive Disclosure。

## 22.4 所有工具一次暴露

后台能力强 ≠ 前台每次必须全部展示。

## 22.5 只看压缩率

最危险。

## 22.6 多层都做 Router

Brain、TokenMind、Skill、MCP 各自一套路由，会产生冲突和重复决策。

## 22.7 每个任务都跑全部测试

测试范围应该与风险/影响范围匹配；关键 Gate 不能省，但不做无意义的全量消耗。

---

# 23. 数据与 Telemetry

建议至少记录：

```text
session_id
agent_id
task_id
skill_id
tool_id
triggered
trigger_reason
context_tokens_loaded
result_tokens
call_count
cache_hit
latency_ms
success
rework
p0_evidence_retained
error_class
```

必须考虑隐私/secret 脱敏，不保存原始敏感输入。

---

# 24. Benchmark 设计

## 24.1 Phase 0 Baseline

真实任务优先，至少覆盖多个复杂度层级。

不要为了凑 50 条造 50 条低质量任务。先做 15–30 条有代表性的高质量任务，逐步扩展。

## 24.2 同任务 A/B

必须固定：

- repo commit；
- model/version；
- task input；
- acceptance criteria；
- 测试环境。

记录随机性，必要时重复多次。

## 24.3 Benchmark 绝不能只包含容易压缩的 Build Log

否则会虚高。

必须包含：

- prose docs；
- code search；
- database；
- debug；
- tests；
- cross-module；
- logs；
- small tasks。

---

# 25. 上线门槛

治理优化进入默认路径前：

### P0 必须

- 正确率 Gate PASS；
- Evidence Gate PASS；
- 安全 Gate PASS；
- 无新增严重冲突；
- Trigger positive/negative/boundary/conflict 测试；
- 回滚方式明确。

### 强烈建议

- ≥3 个真实项目任务 A/B；
- 至少一个复杂 Debug；
- 至少一个跨模块任务；
- 观察实际 Token/Tool/返工数据。

---

# 26. 分阶段开发方案

## Phase 0 — Inventory + Baseline

交付：

```text
skills inventory
mcp/tool inventory
instruction inventory
overlap map
baseline tasks
baseline metrics
```

## Phase 1 — 三个 Doctor

实现：

```text
skill-doctor
mcp-doctor
agents-doctor
```

先做**只读审计 + 报告**，不自动改生产配置。

## Phase 2 — Runtime Policy Integration

接 TokenMind：

- dynamic/lazy load；
- tool exposure budget；
- context budget；
- dedup/cache；
- telemetry。

## Phase 3 — TestMind Closed Loop

把审计变化自动放入：

```text
baseline → change → affected tests → real tasks → compare → verdict
```

## Phase 4 — Multi-Agent Production

重点：

- shared daemon；
- isolation；
- concurrency；
- retry control；
- per-agent telemetry；
- policy consistency。

## Phase 5 — Controlled Self-Optimization

只允许自动：

- 提建议；
- 生成 patch candidate；
- 运行测试；
- 生成报告。

高风险自动删 Skill、改安全权限、改生产 Tool 暂不允许无人审批。

---

# 27. 推荐仓库结构

若未来独立治理项目：

```text
agent-governance/
├─ doctors/
│  ├─ skill/
│  ├─ mcp/
│  └─ instructions/
├─ contracts/
├─ policies/
├─ scanners/
├─ benchmarks/
├─ reports/
├─ fixtures/
├─ schemas/
└─ docs/
```

若暂时不独立项目，先把 Skill Doctor 作为 Skill 落地，Telemetry/Runtime 能力继续归 TokenMind，长期经验归 Brain，验证归 TestMind。

这是当前最稳妥的边界。

---

# 28. Definition of Done

V1 完成必须满足：

- [ ] 有统一 Skill 审计标准；
- [ ] 有统一 MCP 审计标准；
- [ ] 有统一 AGENTS/Rules 审计标准；
- [ ] 有 Progressive Disclosure 标准；
- [ ] 有 Trigger 4 类测试；
- [ ] 有安全供应链审计；
- [ ] 有 100 分评分体系；
- [ ] 有 Hard Gate；
- [ ] 有 Evidence Preservation；
- [ ] 有 Brain/TokenMind/TestMind 职责边界；
- [ ] 有多 Agent MCP 要求；
- [ ] 有真实 E2E A/B 方案；
- [ ] 不把 Tool-level 压缩率冒充整体 Agent 节约率；
- [ ] 有 Rollback；
- [ ] 有至少 3 个真实项目任务验证后，才允许宣称“生产可用”。

---

# 29. 最终设计原则

整套系统最终追求的不是：

```text
最小 Context
```

而是：

```text
Minimum Sufficient Context
最小充分上下文
```

不是：

```text
最少 Tool
```

而是：

```text
Minimum Sufficient Capability
最小充分能力
```

不是：

```text
最高 Compression Ratio
```

而是：

```text
Lowest Successful Task Cost
在保持正确、安全、证据完整前提下，最低成功任务成本
```

最终一句话：

> **未来 Skill 和 MCP 可以越做越强、越做越多，但任意一次任务只加载真正需要的最小充分部分；不必要的内容不进入上下文，重复内容不再次支付 Token，昂贵能力按需展开，关键证据永不丢失。**

---

# 30. 本次附带成熟 Skill

本规范配套 `skill-governance-doctor`，其自身严格采用本规范：

- 根 `SKILL.md` 为小路由器；
- 重内容拆入 `references/`；
- 审计结果使用 `templates/audit-report.md`；
- `tests/pressure-scenarios.md` 提供 Trigger、Evidence、Multi-Agent、安全和诚实度测试；
- 不把运行时 Router 职责抢进 Doctor；
- 不因追求 Token 节约牺牲正确率。

建议先把这个 Skill 放入项目实际使用，再让它反过来审计你现有 Skill/MCP。真实运行数据出来后，再决定是否把 Skill Doctor、MCP Doctor、AGENTS Doctor 拆成 3 个独立 Skill。
