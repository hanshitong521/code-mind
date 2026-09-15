# 三级加载（TokenMind 集成）

> 规格：`references/spec-v2.md` §5 ｜ 方法论：`references/spec-v1.md` §8 渐进式披露、§20 节约优先序 ｜ 硬闸门：`references/testmind.md` Evidence Gate
> 目标：**减少 ≥50% 无效上下文**（不是减少总 Token）。正确率、证据完整性、安全边界永远排在 Token 之前。

## 0 一条公理

**最省 Token 的内容，是根本没必要进入上下文的内容。**

压缩是第 7–8 级手段。先做 1–6 级，永远不要先做压缩；先压缩等于把「不该进来的东西」花钱搬进来再花钱瘦身。

## 1 三级定义与预算

| 级 | 加载内容 | 预算 | 触发条件 | 落点 |
|---|---|---|---|---|
| L0 | `name` + 极短 `description` + `tags` + `score` | ≤ 100 tokens | 常驻（路由期唯一可见面） | `registry.json.skills[]`（`scripts/skillmind.py registry build`） |
| L1 | 根 `SKILL.md`（路由器） | 命中才加载；根 ≤120 行，普通 <500 words，高频常驻 <200 words | 路由命中该 skill | `skills/<skill_id>/SKILL.md` |
| L2 | `scripts/` / `examples/` / `references/` | 执行时按需，**单条单读** | L1 的 `ref:` 路由表命中某一条 | `skills/<skill_id>/references/*.md` |

L0/L1/L2 是**逐级付费**关系：L0 未命中 → 不付 L1；L1 路由未命中 → 不付 L2。

### 1.1 L0 细则

- 四要素缺一不可；`score` 无记录时写 `null`，**禁**用 0 冒充。
- `description` 只回答一个问题：**「这个任务现在是否应该加载我？」** 含 `Use when <精确场景>` + `Not for <易误触发邻域>`。
- 禁：在 description 里写工作流摘要、写「数据库相关」「代码相关」这类一碰领域就触发的宽词（V1 §22.2）。
- 禁：L0 塞项目强约束全文；项目事实归 `references/memory.md` 的项目记忆层。

### 1.2 L1 细则

根 `SKILL.md` 只允许放：frontmatter · 何时用/何时不用 · 路由表 · 不可破 invariant · 最小输出契约。
移出到 L2：API 长文、全场景步骤、重复示例、可由脚本完成的机械检查、项目专属业务规则、其他 skill 已有的通用流程（V1 §6.2）。
**禁为拆而拆**：一次任务要读 ≥5 个碎文件 = 失败，合回去（`references/apply.md`）。

### 1.3 L2 细则

- **单读**：一次任务只读路由表命中的那一条，禁批读整目录。
- 单条 reference 估算 > 2000 tokens → 必须再拆，或改由 `scripts/` 预处理后只回传结论。
- 大结果（日志/查询集/构建输出）**禁**整段进上下文：先 `scripts/` 或 MCP 侧聚类、投影、截断，P0 证据按 `references/testmind.md` 保留。

## 2 Token 节约八级优先序（**顺序不可颠倒**）

| 级 | 手段 | 落地做法 | 预期贡献 | 禁 |
|---|---|---|---|---|
| 1 | **不加载** | 三级加载 + 路由硬过滤（`status=blocked` 永不推荐；`exclude` 命中即排除）+ L1 精确 `trig:` | 最大 | 为「可能有用」预加载整目录 |
| 2 | **不重复加载** | 同 `session_id` 内同一 ref 只读一次；L1 命中后禁再整读 skill 目录；`telemetry.cache_hit` 留痕 | 大 | 同会话反复读同一文件 |
| 3 | **不重复调用** | 同 `tool_id` + 同参数 + 同 `correlation_id` 禁二次调用；MCP Gateway 去重；Retry 有界（`references/spec-v2.md` §4） | 大 | 5 Agent × 3 retry = 15× 重试风暴 |
| 4 | **缓存复用** | 以内容哈希为 key（复用 `_common.hash_tree`，与控制面逐字节等价）；未变则跳过 | 中 | 未变重算 / 重渲 / 重扫 |
| 5 | **增量读取** | 按 offset/limit 分段读；看 diff 不看全文；变更面用 `get_change_context` 取，禁整仓扫 | 中 | 无 orient 整读大文件 |
| 6 | **结构化筛选** | 先 grep/SELECT/字段投影再进上下文；日志按错误签名聚类计数 | 中 | 把原始全量塞给模型自己筛 |
| 7 | **摘要** | 只留结论 + P0 证据指针（路径/行号/错误原文/exit code） | 小 | 摘要掉错误类型与行号 |
| 8 | **深度压缩** | 最后手段；对重复成功日志、同 stack trace 第 N 次重复、无任务相关性 metadata | 小 | 压缩率 98% 但删掉错误证据 → 直接 FAIL |

**颠倒即 FAIL**：跳过 1–6 直接做 7–8，会得到「压缩率漂亮、总成本更高、返工更多」的结果（V1 §2 判 FAIL 条款）。

## 3 各级估算方法

通用折算（零依赖，用于预算核验与报告填报）：

```
est_tokens(s) = ceil(ascii_chars / 4) + ceil(cjk_chars / 1.5)
```

| 对象 | 估算口径 | 核验方式 |
|---|---|---|
| L0 单条 | `name` + `description` + `tags` 拼接 + `score` 字段文本 | `est_tokens(...) ≤ 100`；超限 → 改窄 description，禁删 `Not for` |
| L1 根文档 | 行数（硬指标）+ words | `registry.json` 的 `root_lines` / `root_words`（`scripts/skillmind.py registry build --json`）；> 120 行必须拆 |
| L2 单条 | 单文件 `est_tokens` | > 2000 tokens → 拆或脚本预处理 |
| 运行时真实值 | 遥测实测 | `context_tokens_loaded` / `result_tokens`（`references/spec-v2.md` §14.5） |

**禁**用估算值冒充实测值：报告里估算与实测分列，来源标注 `est` / `telemetry`（`templates/skill-score-report.md`）。

## 4 与 TokenMind 的交接字段

路由结果向 TokenMind 提供（只读消费，TokenMind 不重做业务路由，`references/spec-v2.md` §9.4）：

```json
{"resource":"skill-or-tool-id","domain":"...","estimated_tokens":0,
 "priority":"P0|P1|P2","relevance":0.0,"p0_evidence":false,"lazy":true,"cache_key":"..."}
```

| 字段 | 谁填 | 用途 |
|---|---|---|
| `estimated_tokens` | SkillMind（§3 公式） | 预算分配 |
| `priority` | SkillMind（风险/阶段） | P0 先于 P2 加载 |
| `p0_evidence` | SkillMind | `true` → 禁摘要、禁压缩 |
| `lazy` | SkillMind | `true` → 进 L2，不随 L1 展开 |
| `cache_key` | 内容哈希 | 第 4 级缓存复用 |

## 5 落地检查表

### 5.1 分级

- [ ] L0 四要素齐（`name`/`description`/`tags`/`score`），单条 ≤100 tokens
- [ ] `description` 含 `Use when` + `Not for`，≤1 行，无工作流摘要
- [ ] 根 `SKILL.md` ≤120 行；高频常驻 <200 words；超 800 words 已拆 `references/`
- [ ] `ref:` 路由表**每条一行「信号 → 路径」**，命中才读，写明禁批读
- [ ] 单条 reference ≤2000 tokens；大结果已由 `scripts/` 预处理
- [ ] 一次任务需读的碎文件 <5 个

### 5.2 八级（按序核）

- [ ] 1 不加载：硬过滤（blocked/exclude）先于打分；无误触发金标用例（`tests/trigger-cases.md`）
- [ ] 2 不重复加载：同 session 同 ref 只读一次，有 `cache_hit` 留痕
- [ ] 3 不重复调用：同参数同 `correlation_id` 去重；retry/timeout/queue 有界
- [ ] 4 缓存复用：内容哈希为 key；未变跳过
- [ ] 5 增量读取：diff/分段/变更面，禁整仓扫
- [ ] 6 结构化筛选：grep/SELECT/投影/日志聚类先于投喂
- [ ] 7 摘要：结论 + P0 指针，非全量复述
- [ ] 8 深度压缩：仅在 1–7 做完后；P0 证据清单逐条核对未被删

### 5.3 结论必报

- [ ] 无效上下文下降幅度（目标 ≥50%），**同时**报 `TaskSuccess · InputTokens · OutputTokens · ToolCalls · DuplicateCalls · Latency · Rework · EvidenceRetention` 八项（`references/testmind.md`）
- [ ] 只报压缩率 = 报告作废

## 6 STOP

STOP:颠倒八级序|先压缩后治理|为省 token 删 P0 证据|description 写工作流|description 一碰领域就触发|L0 塞项目强约束|根文档塞参考资料|一次读 ≥5 个碎文件|L1 命中后整读 skill 目录|未变重复加载/重复调用|无 orient 整读大文件|把 10MB 日志塞上下文|估算值冒充实测值|只报压缩率|为「可能有用」预加载|预算超限不拆只删 Not for
