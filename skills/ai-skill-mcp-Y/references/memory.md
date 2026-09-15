# 记忆分层（Brain 集成）

> 规格：`references/spec-v2.md` §6 ｜ 方法论：`references/spec-v1.md` §11 Project Brain 对接 ｜ 上位：`../../shared/core.md`《pipeline-contract》L-WHY 层
> Brain 只回答 **WHY**（为什么这么定 / 踩过什么坑），不回答 WHAT（FROZEN 在 RequirementMind）、不回答 HOW（在 skill）、不做路由。

## 0 三条铁律

1. **项目数据只能进项目 Memory；通用经验才进 Skill Evolution。**
2. **Skill 不保存个人污染数据**（个人偏好、习惯、个人环境路径禁入 Skill 经验）。
3. **未验证的猜测不进 Brain**（两态流转见 §3）。

违反任一 → 该次记忆写入作废，并回滚该条记录。

## 1 四层记忆与归属

| 层 | 内容 | 归属（唯一 Owner） | 可见范围 | 禁 |
|---|---|---|---|---|
| 个人记忆 | 用户偏好、习惯、个人环境约定 | 用户级 | 仅该用户 | 进 Skill 经验；进项目 Brain |
| 项目记忆 | 项目事实、约定、ADR、坑 | 项目 Brain（`search_project_context` / `save_*`） | 该项目全部 Agent | 跨项目共享；携带到公共知识 |
| Skill 经验 | 该技能的成功模式、失效模式、坑 | Skill Evolution（本 skill 的 `references/` 或 skill 目录） | 该 skill 的所有调用方 | 混入个人数据；混入项目专属事实 |
| 公共知识 | 通用最佳实践、栈级通识 | 公共 | 全部项目 | 携带项目敏感信息（表名、内网地址、业务口径、客户名） |

**归属判定三问**（写入前必答，任一答不出 → 不写）：

```
Q1 换一个项目还成立吗？  否 → 项目记忆；是 → 继续
Q2 只对某个人的习惯成立吗？ 是 → 个人记忆，禁入 skill
Q3 是「怎么做」（流程/步骤）还是「为什么/踩了什么坑」？ 怎么做 → 归 skill 正文，不归 Brain
```

## 2 内容归属示例

| 内容 | 正确落点 | 错误落点 |
|---|---|---|
| 该库 `audit_status` 驳回后可重新提审 | 项目 Brain（项目事实） | Skill 经验 |
| MyBatis 动态 SQL 用 `<if test>` 易漏 `and` | Skill 经验（通用坑） | 项目 Brain |
| 用户喜欢先给结论再给证据 | 个人记忆 | Skill 经验 |
| 内网主机 `192.168.x.x` 的日志路径 | 项目 Brain（含敏感 → 脱敏后写） | 公共知识 |
| 该 skill 的 18 步流程 | skill 正文 `SKILL.md` | Brain（Skill 流程副本，禁） |
| 某个 MCP tool 的入参 schema | MCP 自身的 schema 真源 | Brain（Tool Schema 副本，禁） |

## 3 两态流转

```
candidate ──(TestMind / Evidence 验证通过)──▶ verified ──(多次失效 / 版本漂移)──▶ stale / deprecated
    │                                            │
    └── 验证失败 / 被证伪 ──▶ 丢弃（禁升级为 verified）
```

| 态 | 进入条件 | 可被下游依赖？ | 失效处理 |
|---|---|---|---|
| `candidate` | 单次任务观测到的经验、未复现的猜测 | **否**；引用时必须标注「未验证」 | 超期未升级 → 丢弃 |
| `verified` | TestMind 或 Evidence Gate 给出可复现证据（`references/testmind.md`） | 是 | 失效 ≥2 次或版本漂移 → 降级 |
| `stale` | 曾 verified，但环境/版本已变，证据不再成立 | 仅作线索，禁当事实 | 复验通过可回 `verified`；否则 `deprecated` |
| `deprecated` | 多次失效或已被新结论取代 | 否 | 保留（禁删）并指向替代结论 |

**禁**：`candidate` 当 `verified` 用（最危险的记忆污染）；`deprecated` 静默复用。

## 4 与 project-brain MCP 的对接约定

| 工具 | 何时调 | 写/读 | 约定 |
|---|---|---|---|
| `search_project_context` | 任何「当初为啥 / 有没有坑 / 历史怎么定」问题**先查** | 读 | 查完再决定是否问用户；禁跳过直接猜 |
| `get_change_context` | 改 Java/Mapper/接口前取变更面 | 读 | 与 `references/spec-v2.md` §11 控制面只读消费一致；结果作 L1 输入，禁整仓扫 |
| `save_architecture_decision` | 架构/契约级决策落地且**已 FROZEN** | 写 | 只写决策与理由，不复制 `design.md` 全文 |
| `save_bug_memory` | 根因已钉（`references/testmind.md` 证据齐）的坑 | 写 | 必带：症状 / 根因一句 / 证据 / 证伪项 / 复现面 |
| `record_task_outcome` | 任务收尾 | 写 | 写**摘要 + 指标**，不写日志全文；默认进 `candidate` |

写入约定（P0）：

1. **先查后写**：写之前先 `search_project_context` 去重，已有同结论 → 追加证据，禁新建重复条目。
2. **身份齐全**：写调用必须带 `agent_id` / `project_id` / `session_id` / `correlation_id`（`references/spec-v2.md` §4），缺任一 → 拒绝写入（防记忆污染与串数据）。
3. **幂等**：同 `correlation_id` 重复写 → 只落一条。
4. **脱敏**：secret / 凭证 / cookie / 原始敏感输入**禁**入 Brain（V1 §23）。
5. **有界**：单条记忆写摘要 + 指针（路径/行号/错误原文短片段），**禁**粘贴长文。
6. **可回滚**：每条记录保留来源（task_id / commit / 证据引用），便于降级与撤回。

**与 `search_knowledge` + `build_task_context` 禁同开**（`../../shared/core.md` L-WHY 行）。

## 5 不进 Brain 的内容清单

| 类别 | 为什么禁 | 正确去处 |
|---|---|---|
| 未验证的单次猜测 | 会污染多 Agent 长期判断 | 留在本次会话；验证后再进 `candidate` |
| 日志全文 / 大结果集 | Token 成本高、无长期价值 | 会话内；只把 P0 证据片段写入 |
| Skill 流程正文副本 | 双写 → 漂移；SSOT 在 skill | skill 自身 `SKILL.md` / `references/` |
| Tool Schema 副本 | Schema 真源在 MCP | MCP 服务端 schema |
| 短生命周期临时状态 | 过期即误导 | 会话状态 / `.skillmind/` 生成物 |

判定句：**「这条内容半年后还成立吗？还是需要时能从真源重新取到？」** 半年后不成立、或可从真源重取 → 不进 Brain。

## 6 隔离与脱敏

- 记忆按 `project_id` 隔离；跨项目复用前必须走公共知识层（脱敏 + 通用化）。
- 跨 `agent_id` 共享记忆时，`candidate` 态不得共享。
- 遥测与记忆都不保存原始敏感输入（V1 §23）。

## 7 检查表

- [ ] 写入前已回答归属三问，落在正确层
- [ ] 项目事实进项目 Brain，通用经验进 Skill 经验，个人偏好留在个人层
- [ ] Skill 经验中无个人污染数据、无项目敏感信息
- [ ] 每条记忆有明确态：`candidate` / `verified` / `stale` / `deprecated`
- [ ] `candidate` 未被下游当事实依赖
- [ ] 写调用带齐 `agent_id` / `project_id` / `session_id` / `correlation_id`，且已去重
- [ ] 五类禁入内容（§5）一条未进 Brain
- [ ] 记忆内容已脱敏，且为摘要 + 指针而非长文

## 8 STOP

STOP:未验证猜测当事实|项目数据写进 Skill 经验|个人数据写进 Skill 经验|项目记忆跨项目共享|公共知识携带敏感信息|candidate 当 verified|deprecated 静默复用|日志全文入 Brain|Skill 流程副本入 Brain|Tool Schema 副本入 Brain|临时状态入 Brain|写前不 search 直接写|缺身份字段仍写|重复条目重复写|凭证入 Brain|与 search_knowledge+build_task_context 同开|静默删记忆（只降级）
