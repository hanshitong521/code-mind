# integration.md — 与现有项目整合（spec-v2 §11 / §0.1）

> 读者=Agent。命中「交接物 / 控制面消费 / 五层栈边界 / 哈希 / DRIFT」时读本文件。
> 上位规格：`spec-v2.md` §11（整合）、§0.1（五层栈禁双开）、§9.4（唯一权威路由）、§16（DoD）；
> 公理层：`shared/core.md`《pipeline-contract》《第一性原则》。

---

## 1. 一句话边界

```
RequirementMind  → WHAT     做什么（FROZEN 决策）
project-brain    → WHY      为什么 / ADR / 坑
TokenMind        → CTX      读多少 / 从哪读
SkillMind        → HOW-选   选哪个技能 / 用什么链 / 暴露多少工具   ← 本 skill
ai-code/ai-design→ HOW-做   怎么写
TestMind         → VERIFY   真的成了吗
Evidence Gate    → 证据     能不能证明
```

**SkillMind 只做「选」。** 一旦开始写业务码、改生产配置、改需求决策，即越界（spec-v2 §0.1 / V1 §22.6 禁多层 Router）。

| 越界信号 | 正确做法 |
|---|---|
| 直接改 `docs/diagram/*` 或业务源码 | 交回 `/ai-design` / `/ai-code` |
| 自行判定 FROZEN 决策对错 | 交回 RequirementMind（`DEVELOPMENT_BLOCKER`） |
| 自己写第二套 Router | 运行时权威只有 SkillMind Router（§9.4），其余层只提供信号 |
| 反向改写 `shared/*.yaml` | 只读消费，见 §3 |

---

## 2. 交接物表（spec-v2 §11）

| 系统 | 层 | 职责 | 交接物（方向） | 消费方如何使用 |
|---|---|---|---|---|
| RequirementMind | L-WHAT | 冻结需求 | `decisions.json` FROZEN → **路由输入** | 取项目类型 / 复杂度（L0–L3）/ 风险等级作为 Router 入参；不改决策内容 |
| SkillMind | L-HOW-选 | 选 | `registry.json` + `route-result.json` → **出** | 下游按 `recommended` / `chain` 执行；按 `excluded` 的理由避免误用 |
| TokenMind | L-CTX | 读多少 | 路由结果里的 `estimated_tokens` / `load_level` → **出** | 由 TokenMind 决定实际加载量与读取顺序（SkillMind 只给预算建议） |
| Brain | L-WHY | 记住 | `candidate` 经验 →（验证后）`verified` | 项目事实进项目 Brain；通用经验才进 Skill Evolution（spec-v2 §6 铁律） |
| TestMind | L-VERIFY | 验证 | `Skill Score Report` → **出** | 上线门槛判定；SkillMind 只消费结论，不自行宣布 PASS |

交接物契约位置（`shared/schema-versions.yaml` 注册）：

| 交接物 | 契约 | 生产者 | 消费者 |
|---|---|---|---|
| `registry.json` | spec-v2 §14.2 | `scripts/registry_build.py` | Router、评分引擎、审计 |
| `route-result.json` | spec-v2 §14.3 | `scripts/router.py` | TokenMind、执行层 Agent |
| `score-record.json` | spec-v2 §14.4 | `scripts/score.py` | 进化生命周期、Skill Score Report |
| telemetry 事件 | `schemas/telemetry-event.schema.json` | `scripts/telemetry.py` | summary 聚合、告警 |
| `Skill Score Report` | `templates/skill-score-report.md` | SkillMind | TestMind、上线门槛 |

**规则**：SkillMind 的输出**不含**「已实现」「已修复」这类宣称。
它只输出「选了谁、为什么、排除谁、为什么排除」——宣称属于 L-DO 与 L-VERIFY。

---

## 3. 与本仓控制面的只读消费关系（spec-v2 §11）

SkillMind 是控制面的**消费者**，不是生产者。四个文件全部**只读**：

| 文件 | 用途（消费什么） | 消费点 |
|---|---|---|
| `shared/release-manifest.yaml` | 技能清单 + `content_hash` + `artifact_path` → 注册表 `bundled` 与 `hash` 来源 | `_common.CONTROL_PLANE["release_manifest"]` |
| `shared/capability-registry.yaml` | `capabilities` / `phases` / `tool_budget` → 阶段映射与工具预算 | `gateway.md` §4.3；`_common.CONTROL_PLANE["capability_registry"]` |
| `shared/schema-versions.yaml` | 契约版本注册 → 版本兼容判定 | `_common.CONTROL_PLANE["schema_versions"]` |
| `deploy.bundle.yaml` | 分发清单 → `bundled` 判定 | `_common.CONTROL_PLANE["deploy_bundle"]` |

装载入口：`_common.load_control_plane()`（一次性装载四个，缺失返回 `None` 不抛异常）。

### 3.1 只读消费，禁反向改写

```
SkillMind  →  read  →  shared/*.yaml + deploy.bundle.yaml
SkillMind  -×- write -× 上述任何文件
```

禁令（违反即 FAIL）：

| 禁 | 原因 |
|---|---|
| 改 `release-manifest.yaml` 的 `content_hash` / `artifact_path` | 哈希真源只有一个（`scripts/_release_lib.py` 的 build 流程）；改它 = 掩盖漂移 |
| 改 `capability-registry.yaml` 的 `owner` / `phases` / `tool_budget` | 归属声明是控制面契约（I-01 单一权威 Owner）；SkillMind 不得为自己加 owner |
| 改 `schema-versions.yaml` 的版本号 | 版本升格是 breaking change 决策，不是消费行为 |
| 改 `deploy.bundle.yaml` 的 `skills` | 分发清单是发布动作，须人工/发布流程改 |

SkillMind 的**唯一写入面**是 `<repo>/.skillmind/` 生成物目录
（`registry.json` / `scores.json` / `telemetry.jsonl`），且该目录位于仓根、
不进任何 `artifact_path`，因此不影响 `content_hash`（`_common.py:41`）。

### 3.2 `owner` / `phase` 取值必须合法

`scripts/validate_bundle.py:35-40` 是 owner/phase 的合法集合真源：

```python
VALID_OWNERS = {requirement-mind, project-brain-agent, token-mind,
                test-mind, concise-mind, ai-programming-docs, git}
VALID_PHASES = {requirement, design, coding, debug, verification, review, all}
```

推论（写文档/写脚本时必须遵守）：

1. 任何引用 owner 的地方只能用上表七个值。**SkillMind 不在其中**——
   它是 skill（`skill.yaml: owner: ai-programming-docs`），不是能力 owner。
   因此**禁**向 `capability-registry.yaml` 的 `capabilities` 新增 `owner: skillmind` 条目。
2. 任何引用 phase 的地方只能用上表七个值；`coding,debug` 这类逗号多值写法按单值逐个校验。
3. SkillMind 消费 `phases` 做**阶段 → 能力**映射（`gateway.md` §4.3），
   不新增 phase、不改能力归属。

### 3.3 哈希语义：必须复用 `_common.hash_tree`

```
content_hash 真源语义 = scripts/_release_lib.py: normalize_bytes + hash_tree
SkillMind 侧唯一合法实现 = skills/ai-skill-mcp-Y/scripts/_common.py: hash_tree
```

两者必须**逐字节等价**：

| 语义 | 取值 |
|---|---|
| 算法 | `sha256` |
| 行尾归一 | CRLF → LF，单独 CR → LF |
| 行尾空白 | 每行 `rstrip` |
| 排除文件名 | `.gitignore`、`evals.json`（来自 `release-manifest.yaml: hash.normalize.exclude`，经 `_common.manifest_exclude()` 读取） |
| 排除目录 | `.git`、`__pycache__`、`node_modules`、`.codehealth`、`reports`（`_common.IGNORED_DIR_PARTS`） |
| 目录哈希 | 对「相对路径排序后的 `rel:hash` 行」再做一次 sha256 |

**为什么必须复用**：若 SkillMind 自己实现一份哈希（比如忘了 `rstrip`、或用了 `\r\n` 未归一、
或把生成物目录算进去），同一份源码会算出两个哈希，`verify` 就会报**假 DRIFT**——
修不完的「漂移」全是自己造的。生成物目录（`.codehealth/`、`reports/`、`.skillmind/`）
每次运行都变，算进哈希只会让 CI 里的 `--check` 反复报假 DRIFT。

因此：**任何需要内容哈希的地方一律 `from _common import hash_tree`，禁自写 `hashlib.sha256` 遍历**。

### 3.4 与 `validate_bundle.py` / `verify_skill_drift.py` 的关系

- 本 skill **不修改**这两个脚本（属于发布控制面）。
- 本 skill 的产物不得让它们报错：`owner`/`phase` 合法（§3.2）、
  不新增 `schema-versions` 契约条目（新增会导致 `contracts.<name>.file` 必须存在）、
  不改 `deploy.bundle.yaml`（§3.1）。
- DoD 要求：`selftest` 全绿且**不破坏**这两个脚本的既有基线（spec-v2 §16）。

### 3.5 事实记录（当前状态）

- `skills/ai-skill-mcp-Y` **未**出现在 `deploy.bundle.yaml: skills`（当前为
  `ai-design` / `ai-code` / `ai-requirement` / `ai-concise`），也**未**出现在
  `shared/release-manifest.yaml: skills`。即：本 skill 当前不进分发 bundle、
  无 `content_hash` 登记 → 注册表中其 `source` 只能为 `filesystem`、`bundled = false`。
- 这不是缺陷，是**发布决策**；若要纳入分发，需改 `deploy.bundle.yaml` +
  `release-manifest.yaml`（属发布流程，不属本 skill 的写入面）。

---

## 4. 与五层栈的边界细则（shared/core.md）

| shared/core.md 层 | 系统 | SkillMind 的关系 | 禁 |
|---|---|---|---|
| L-WHAT | RequirementMind | **输入**：FROZEN 决策 → 项目类型/复杂度/风险 | 猜 WHAT；改决策；用记忆覆盖 FROZEN |
| L-WHY | project-brain | **双向受限**：读历史成功率作路由信号；写回仅 `candidate` 经验 | 项目数据进 Skill 经验；跨项目共享 |
| L-CTX | TokenMind | **输出建议**：`estimated_tokens` / `load_level` | 自己决定整读；绕开 TokenMind 直接全量加载 |
| L-HOW | `/ai-design` | **相邻不重叠**：设计层定「系统怎么长」，SkillMind 定「用哪个技能做」 | 画节点/写设计交付 |
| L-DO | `/ai-code` | **相邻不重叠**：SkillMind 只给「选」的结果 | 写业务码、改生产配置、宣称已修复 |
| L-VERIFY | TestMind | **消费结论**：只读 `Skill Score Report` | 自行宣布 PASS；跑全量测试 |

冲突裁决序（`shared/core.md`）：`项目 AGENTS/rules > shared/ 契约文档 > 各 SKILL.md 展开`。

### 4.1 记忆分层铁律（spec-v2 §6）

```
个人记忆 → 用户级       禁：进 Skill 经验
项目记忆 → 项目 Brain   禁：跨项目共享
Skill 经验 → Evolution  禁：混入个人数据
公共知识 → 公共         禁：携带项目敏感信息
```

SkillMind 只把**通用**成功模式/坑写进 Skill Evolution；
`project_id` 相关的任何内容留在项目 Brain，且聚合时按 `project_id` 过滤。

---

## 5. 集成自检清单

- [ ] 是否只输出「选」的结果，未越界到「做」？
- [ ] 是否只读消费四个控制面文件，未反向改写？
- [ ] 引用的 `owner` / `phase` 是否都在 `VALID_OWNERS` / `VALID_PHASES` 内？
- [ ] 是否未向 `capability-registry.yaml` 新增 `owner: skillmind`？
- [ ] 需要内容哈希的地方是否复用 `_common.hash_tree`（未自写 sha256 遍历）？
- [ ] 写入是否只发生在 `<repo>/.skillmind/`？
- [ ] 聚合/沉淀是否按 `project_id` 过滤，未跨项目合并？
- [ ] 是否未让 `validate_bundle.py` / `verify_skill_drift.py` 报新错？

## 6. 反模式（违反即 FAIL）

| 反模式 | 为什么错 |
|---|---|
| SkillMind 反向改写 `shared/*.yaml` | 消费方改真源 = 契约失效，漂移不可追 |
| 自写哈希遍历 | 与 `_release_lib` 语义不一致 → 假 DRIFT |
| 把生成物目录算进 `content_hash` | 每次运行都变 → CI 反复假 DRIFT |
| 向 capability-registry 新增 owner | `owner` 必须 ∈ `VALID_OWNERS`，否则 `validate_bundle.py` FAIL |
| 多层都做 Router | 冲突 + 重复决策（spec-v2 §15） |
| SkillMind 宣布「已修复 / PR-ready」 | 宣称属 L-DO / L-VERIFY，越界 |
| 项目数据进 Skill 经验 | 违反记忆分层铁律，跨项目污染 |
