# shared/core.md (merged SSOT)

---
<!-- was pipeline-contract.md -->

# pipeline-contract · 五层唯一职责（禁双开）

> 读者=Agent。冲突裁决：项目 AGENTS/rules > 本文件 > 各 SKILL 展开。

## 层（上→下；下层禁改上层真源）

|层|系统|管什么|真源|禁|
|---|---|---|---|---|
|L-WHAT|RequirementMind|做什么；FROZEN|`.requirementmind/decisions.json` + Gate|未 READY 正式开发；用记忆覆盖 FROZEN|
|L-WHY|project-brain|为什么/ADR/坑|MCP `search_project_context` `get_change_context` `save_*`|查 Java 位置；与 `search_knowledge`+`build_task_context` 同开|
|L-CTX|Token-Mind/ContextMind|读多少/从哪读|`context_orient`→`context_fetch`；`.contextmind/task.active.json`|无 orient 整读 `*ServiceImpl`>80；第二套 Explore|
|L-HOW|`/ai-design`|怎么做本期切片|plan + Handoff YAML|同 chat 写码；重问 WHAT（FROZEN 已钉）|
|L-DO|`/ai-code`|最小 diff + 自检|Change Manifest + LOCAL SELF-CHECK|未绿宣称完成；猜契约|
|L-STYLE|`concise-mind`|说话/diff 胖瘦（可选叠加）|仅 `/concise-mind` 挂上|当工作流；跳闸门；常驻 L0；替 ponytail 技能整读|

## 路由（用户一句 → 首挂）

|信号|首|勿叠|
|---|---|---|
|模糊需求/多解读/未钉金标|RM 若未 Gate；否则 `/ai-design`|`/ai-code`|
|Gate READY 且 HOW 未钉|`/ai-design`|再开 RM grilling|
|改 Java/SQL/修 bug|`/ai-code`|`grilling`；无 orient|
|一直修不好|`/ai-debug`→`/ai-code`|未复现改|
|「当初为啥」/ADR/坑|brain `search_project_context`|当代码图|
|长任务续做|TaskBundle + `.agent/state`|靠 chat 历史|
|diff 太胖/说人话|`@concise-mind`（可与 `/ai-code` 同挂）|当拷问；Read ponytail SKILL|

Grill SSOT：RM 未 READY → 只用 RM Phase3；Gate READY 后 HOW 拷问 → `/ai-design` 写前门。禁同 chat `ai-code`+`grilling`。`concise-mind` 不是 grilling。

## 冲突

1. FROZEN ≠ 代码/SELECT → `DEVELOPMENT_BLOCKER` 回 RM（禁 ai-code 私裁）
2. FROZEN ≠ brain 记忆 → **FROZEN 赢**；brain 只作旁证；须 supersede 才改决策
3. Handoff 范围 ≠ TaskBundle `allow_globs` → 以 Handoff 变更面改 bundle 后再写码
4. 验证档位：Handoff enum > verification-gate 表 > 自拟清单

## 工件链（fail-closed）

```
RM Gate READY
  → sync FROZEN: decision_state.json + `node scripts/sync-requirementmind-brain.mjs`
  → /ai-design: plan + yaml Handoff
  → `python scripts/validate_handoff.py` PASS
  → `python scripts/validate_handoff.py to-bundle <handoff> -o .contextmind/task.active.json`
  → /ai-code: orient1 → 最小 diff → LOCAL SELF-CHECK
  → Change Manifest（code_to_test 字段）
  → brain: `record_task_outcome`（摘要）+ 必要时 `save_architecture_decision`/`save_bug_memory`
```

无 Handoff 的 micro-fix（typo/唯一解读）：可跳 design；仍须 G0 判据 + 档位 m/l。

## 命令

|何时|cmd|
|---|---|
|RM 出口|`node $SKILL/scripts/state.mjs gate .requirementmind`|
|RM facts 缓存|`node $SKILL/scripts/state.mjs facts-stale .requirementmind [--write]`|
|RM→manifest|`node $SKILL/scripts/state.mjs manifest .requirementmind`|
|Handoff|`python scripts/validate_handoff.py <file>`|
|Handoff→bundle|`python scripts/validate_handoff.py to-bundle <handoff> -o .contextmind/task.active.json`|
|bundle|`node .cursor/contextmind/cli.mjs task validate`|
|路由|`node .cursor/contextmind/cli.mjs task route`|
|一张图|`node .cursor/contextmind/cli.mjs task manifest`|
|成绩单|`node .cursor/contextmind/cli.mjs scorecard` / `report`|
|Java 结构|MCP `context_orient` 一次；禁同符号再 orient|

## 接入门

涉 DB/SSH：Handoff `接入门: 已填|跳过(原因)`。静默降级=STOP。

---
<!-- was first-principles.md -->

# 第一性原则（First Principles）

> 三 Skill 体系的**公理层**——从公理推导流程，而非堆砌流程口号。
> 与 [glossary.md](glossary.md)（词汇 SSOT）并列。

---

## 公理层级（冲突裁决序）

```
项目 AGENTS.md / .cursor/rules/          ← 实例覆盖（最高）
         ↓
本文件 6 公理 + shared/ 契约文档           ← 体系 SSOT
         ↓
各 SKILL.md 执行指针 + references/          ← 场景展开（最低复述）
```

**复述禁令**：同一规则只在 SSOT 处完整定义；SKILL.md 留**指针 + 最小执行清单**，禁止复制整段。

---

## 六条公理

### 0. 前提先于推进（Premise Before Proceed）

动手/长答前先审用户表述。错前提、逻辑跳跃、信息缺失、未证实判断 → **指出并停推**，禁顺着错帧实现。

| 标签 | 含义 | 可写进交付？ |
|------|------|--------------|
| 事实 | 本轮工具/源码/SELECT/官方文档已见 | 是 |
| 推测 | 合理但未 Fresh 验证 | 须标「推测」 |
| 观点 | 取舍/偏好 | 须标「观点」 |
| 不可验证 | 缺源/缺环境/缺判据 | 须说明缺什么；禁当事实 |

硬动作：
- 缺完成判据 / ≥2 解读 → 问清或 `/ai-design`（禁抢跑）
- 用户前提与 Explore/SELECT 冲突 → 先拆前提；禁谄媚顺着改码
- 用户顶结论 → HOLD+证据 或 CHANGE+新证据；**禁无证据翻盘**
- 涉数字/人物/日期/引用 → 核对来源；不能确认就写不可验证

对照表（社区翻车→本门）：skill-meta/references/forum-distill.md

### 1. 证据先于宣称（Evidence Before Claims）

未 **Fresh** 跑完验证，禁止输出「已完成 / 已修复 / PR-ready / 全部 PASS」。

- 编码：`verification-gate.md` 五步法
- 测试：报告只写**实际跑过**的 SQL/HTTP
- 设计：验收表每行须写明**哪一种**验证（compile / SELECT / lint / API）
- **反模式**：`compile 绿` ≠ `行为正确`——过滤/权限类须跑身份×入参全矩阵（verification-gate，禁组合级 skip）

### 2. Explore 先于写入（Explore Before Write）

表名、接口、字段、配置须 **Read/Grep/codegraph 见到**再写；禁止凭记忆、旧 runner 常量或训练数据**幻读**。

- 设计：模块地图来自 Explore，非编造
- 编码：Step 2 复用检查 + SELECT 来源对比
- 测试：夹具主键来自**当次 plan + SELECT**

### 3. 证伪先于实现（Falsify Before Implement）

数据类 Bug：**改前 SELECT 对齐用户预期** → 不对齐则停改代码、回设计；对齐后才改 Mapper/SQL。

- 证伪 → 不改代码（三 Skill 一致）
- 证实 → 最小改动 + 改后 SELECT + compile
- **先证「是不是 Bug」**：症状可能是设计允许的回流/空语义/环境错位 → 见 [false-alarm-missed-detection.md](false-alarm-missed-detection.md)；假阳性则**改动为零**

### 4. 单一事实源（Single Source of Truth）

| 含义 | SSOT 位置 |
|------|-----------|
| 词汇 | [glossary.md](glossary.md) |
| 场景-行为表 / 穷举维 | ai-code verification-gate |
| 假阳性与漏检防火墙 | [false-alarm-missed-detection.md](false-alarm-missed-detection.md) |
| 身份×入参组合矩阵 | ai-code verification-gate 身份维 |
| 验证升档 | verification-policy.yaml（risk→gate） |
| 验证档位 | [verification-gate.md](../skills/ai-code/references/verification-gate.md) + [verification-policy.yaml](../verification-policy.yaml) |
| 五层栈 | [pipeline-contract.md](pipeline-contract.md) |
| Handoff 字段 | [handoff-schema.yaml](handoff-schema.yaml) |
| 跨 Skill 衔接 | [handoff-schema.yaml](handoff-schema.yaml) · design handoff-template |

违反 SSOT = **复述** → token 浪费 + 维护漂移。

### 5. 最小有效改动（Minimal Effective Change）

只实现用户要的；**grep 复用优先于新建**；Bug 修共享 choke point，不只 patch 报告路径。

- YAGNI 决策梯：[reuse-patterns.md](../skills/ai-code/references/reuse-patterns.md)（节「YAGNI 决策梯」；上游 `ponytail` 全文按需装）
- 复用门禁：写新类/方法/SQL 前先过 grep 表
- 精准改动：不顺手改相邻代码/格式
- **语义守恒硬边界**：提速/精简 diff **≠** 删生效业务口径。Musk「删>优」只删死代码/未用开关/YAGNI 预留；**指标公式、兜底行、状态边、权限谓词**须保留或经 `/ai-design` 迁到等价实现并对拍。词汇 SSOT：[glossary.md](glossary.md)#语义守恒

---

## 公理 → Skill 映射

栈职责（WHAT/WHY/CTX/HOW/DO）只在 [pipeline-contract.md](pipeline-contract.md)；下表不复述。

| 公理 | ai-design | ai-code |
|------|-----------|---------|
| 前提先于推进 | G-pre；≥2 解读先问；FROZEN 优先；禁顺着错需求写 plan | G-pre；错前提 STOP；FROZEN≠代码→BLOCKER；期望=Handoff+证据 |
| 证据先于宣称 | 验收表可检查；Handoff 须 validate | verification-gate；Change Manifest=code_to_test |
| Explore 先于写入 | 模块地图 + 复用盘点；orient1 | orient/codegraph 一次；reuse grep；夹具 SELECT |
| 证伪先于实现 | 验收写 SELECT；回流≠bug | false-alarm 先；SQL 证伪不改代码 |
| 单一事实源 | 引用 SSOT；不复制 PRD | 档位→verification-gate；栈→pipeline-contract |
| 最小有效改动 | Out of Scope；语义守恒验收 | 复用+YAGNI；身份矩阵禁 skip |

---

## 执行铁律（防 execution lapse）

Agent 常见失败：**不 Read reference 就执行**。以下三条 SKILL 层强制：

1. **命中「必读 Reference」表 → 必须先 Read 对应文件再动手**
2. **Handoff 须为结构化 YAML**（`validate_handoff.py` 可过）
3. **完成前对照档位**：local-fix 验证不得宣称 PR-ready
4. **接入门**：任务涉及数据库读写或服务器（SSH/部署/远程排查）时，**先结构化提问收集连接**；用户显式「跳过/暂不连」才降级，且 Handoff 须标注 `接入门: 跳过(原因)`。凭证脱敏不进 Handoff（覆盖旧「静默降级」行为）。

---

## 反模式速查

| 反模式 | 违反公理 | 正确做法 |
|--------|----------|----------|
| 错前提仍开写 plan/码 | 0 | 拆前提；STOP 或改判据 |
| 缺判据抢跑实现 | 0 | 问清或 /ai-design；模糊慢贵→ /ai-design 写前门 |
| 无证据因用户顶嘴改结论 | 0 | HOLD/CHANGE+新证据 |
| 未跑 SELECT 写「SQL 验证通过」 | 1 | Fresh 跑 + Handoff 附结果（cmd+exit） |
| plan 编造表名 | 2 | Explore 后写 |
| 用户假设错仍改 Mapper | 3+0 | 证伪停改，回设计 |
| 三处重复写 DB 连接规则 | 4 | 只在一处定义 |
| 复制 SQL 整段只改 WHERE | 5 | 复用/扩展现有查询 |
| 场景矩阵只列主流程 | 2+1 | 七维穷举 + skip_reason |
| compile 绿即宣称修复（过滤/权限类） | 1 | verification-policy 升档 + 身份矩阵全跑 |
| 权限维只写 1 条验收 | 2+4 | 身份×入参组合穷举 |
| 为提速删掉仍生效的公式/兜底/状态边 | 5 | 先钉语义；换路径须对拍；删口径须 design+用户确认 |
| 裸 ✓ /「应该过了」当验证 | 1 | verification-gate：cmd+exit 或 SELECT 摘要 |

---
<!-- was glossary.md -->

# Skill 词汇（精简版）· 与三 SKILL.md 的 lex 对齐

| 词 | 含义 |
|----|------|
| 负代码 | 删除 > 复用 > 简化 > 扩展 > 新建 |
| 变更面 / Handoff | design 产出范围与验收；yaml 须过 validate_handoff |
| 验证档位 | micro-fix / local-fix / surface / pr-ready；见 verification-gate + verification-policy.yaml |
| 完成判据 | compile + 触及单测 + SQL 探针；禁裸 ✓ |
| 证伪 / 假阳性 | 先数据否定再改码；见 false-alarm-missed-detection.md |
| 语义守恒 | 提速不删生效口径、权限谓词、状态边 |
| FROZEN | RequirementMind 决策；冲突回 RM，禁 ai-code 私裁 |
| 接缝 | 新逻辑挂现有 API，禁静默换契约 |
| 规则演进 | 跨任务重复坑 → brain / pitfalls，禁一例升 STOP |

细节 SSOT：`pipeline-contract.md`、`first-principles.md`。

---
<!-- was false-alarm-missed-detection.md -->

# 假阳性与漏检防火墙（False Alarm / Missed Detection）

> **跨 Skill 通用 SSOT**（设计 / 编码 / 测试 / 日志排查共用）。  
> 勿在各 SKILL.md 复制全文；只引用本文件。  
> 实例（品牌审核回流）仅作附录，规则本身与业务无关。

---

## 一句话

**先分清「设计允许的行为」与「缺陷」；再用同环境证据证伪；最后才改代码。**  
漏检往往不是少测一行，而是**测错对象 / 测不全生命周期 / 把预期当故障**。

---

## A. 假阳性分类（看起来像 Bug，其实不是）

| ID | 类型 | 典型用户话术 | 先做什么 | 判定 |
|----|------|--------------|----------|------|
| F1 | **生命周期回流** | 「驳回/取消/释放后再操作又变回待审/草稿」 | 查设计/代码是否「重新提审/重开单」 | 允许回流 → `expected_lifecycle`，禁修 |
| F2 | **态字段看错** | 「状态没变」 | 对齐列名/别名/`information_schema`；区分业务态 vs 展示态 vs 类型字段 | 看错列 → 纠正观测，非改库 |
| F3 | **环境/主键错位** | 「测试没问题 / 生产有问题」混谈 | 报案 id 在**当前可查库**是否存在；日志主机 vs MCP/测试库 | id 不命中 → 禁用 A 环境结论修 B |
| F4 | **请求未达写路径** | 「我点了驳回还是旧态」 | 日志是否有**同 id** 的 UPDATE/写接口行；仅有 create/add | 无写日志 → 先证请求/权限/路由，禁断定「UPDATE 写错」 |
| F5 | **时间戳未变** | 「改了但没生效」 | `create_time == update_time`（或版本号未增） | 强信号：成功写路径未发生 |
| F6 | **前端乐观更新** | 「页面显示已驳回，刷新又回来」 | 成功回调是否只改本地行、未刷新；对比 DB | FE 本地态 ≠ 落库 |
| F7 | **侧效门禁** | 「新增后立刻锁/采/下单失败」 | 设计是否要求「通过后方可」 | 待审拒绝侧效 = 正确门禁 |
| F8 | **空结果语义** | 「查不到就是 Bug」 | 空=无数据 / 无权限 / 未匹配，契约写清了吗 | 按契约；禁一律当故障 |
| F9 | **幂等/重复提交** | 「点两次还是那样」 | 是否设计幂等成功或拒绝重复 | 对照预期行为表 |
| F10 | **单接口绿≠系统对** | 「审核接口测过了」 | 是否覆盖回流边、侧效、列表可见性 | 局部 PASS 不能结案状态机 |

**处理**：命中 F1–F10 → Handoff/报告标对应 ID；**禁止**在未证伪前写 CAST/改字段/改文案式「修复」。

---

## B. 漏检分类（本该拦住，却没拦住）

| ID | 环节 | 漏了什么 | 以后强制 |
|----|------|----------|----------|
| M1 | 设计 | 预期行为表只有 happy path，无**回流/重入/拒绝侧效** | 状态机类：正向边 + 回流边 + 非法边 ≥1 各一条 |
| M2 | 设计 | 未写「同业务键再提交 = 更新同主键 / 新插」 | Implementation Decisions 写清 |
| M3 | 设计 | 字段语义多义（审核态/货架态/类型）未拆开 | 不变量表按**真实列**分行 |
| M4 | 编码 | 无反馈环就提修复（猜方言/CAST/默认值） | Phase 0 环红/绿；环绿且符合 F1 → 停修 |
| M5 | 编码 | 只改一条写 SQL，未 grep 兄弟读谓词 | 状态机 surface：全触达清单 |
| M6 | 测试 | 只测「通过/驳回」单 API | 矩阵含：回流、重复提交、侧效拒绝、终态列表 |
| M7 | 测试 | 只 API code=200，无 DB 断言 | 写后 SELECT 状态 + update_time/版本 |
| M8 | 测试 | 夹具 id 与报案环境不一致仍报 PASS | precondition 写环境；id 不存在 → `blocked` |
| M9 | 日志排查 | 只看 error，不核对写路径 info | 声称的写操作必须有同 id 日志 |
| M10 | 协作 | FE/BE 未对契约就开修一端 | 先对齐入参字段名与枚举，再定责任端 |

---

## C. 四门禁清单（按 Skill 执行）

### C1 · `/ai-design` 写 plan 前

- [ ] 状态/阶段字段：不变量表含**每一合法态**
- [ ] **回流边**：失败/驳回/取消后再进入主流程 → 目标态写死（回待审 / 保持终态 / 禁止）
- [ ] **非法边**：未达某态时的侧效（锁、扣减、发货、采集）→ 拒绝文案
- [ ] 同业务键再提交：同主键 UPDATE vs INSERT（二选一写进 Decisions）
- [ ] 易混字段分列（如 type / shelf / audit / del_flag）
- [ ] 验收表 ≥1 条「回流」或显式 `skip_reason: 无回流需求`

### C2 · `/ai-code` 与难 Bug（含 debug 流程）

- [ ] 症状匹配 F1–F10？先归类，再决定是否编码
- [ ] 同环境：报案主键 SELECT 命中
- [ ] 写路径：日志或审计有同 id 写操作；或 `update_time` 已变
- [ ] 反馈环：一条命令能对准**用户原话症状**（不是「接口 200」）
- [ ] 环已绿且属 F1/F7 → 输出「非缺陷」+ 设计引用，**不改生产逻辑**
- [ ] 前端契约已核对（字段名 / 枚举）再怪后端或反之

### C3 · `/ai-code` LOCAL SELF-CHECK

- [ ] 状态机默认集（可裁剪，裁须 `skip_reason`）：

| 边 | 断言要点 |
|----|----------|
| 创建/进入初始态 | 状态列 + create |
| 合法前进 | 新状态 + update/version 变 |
| **回流**（若设计有） | 同业务主键；状态回约定态 |
| 非法重复 | 拒绝码/文案 |
| 未达态侧效 | 拒绝 |
| 终态后列表/详情可见性 | 与门禁一致 |

- [ ] 每条写路径场景：API **且** DB（或存储）双断言
- [ ] 回流被设计允许 → 结果记 `PASS (expected_lifecycle)`，**禁止**当 FAIL 开修单
- [ ] 环境写在矩阵 precondition；跨环境 id → `blocked_by: env_mismatch`

### C4 · 项目本地只读排查（shejiuPro sj-log 及同类）

- [ ] 主机分流后，日志里的业务 id 与可查库对齐
- [ ] 用户声称的写操作 → grep 写接口/UPDATE 关键字 + **同一 id**
- [ ] 仅 add/create 无 update → 优先 F4/F5，非「字段写错」
- [ ] 症状像回流 → 对照设计；可重放最小全链路后再下「根因一句」
- [ ] 单接口重放成功 ≠ 全生命周期无问题（标「未覆盖边」）

---

## D. 证据优先级（通用）

```
1. 设计/契约（预期行为表、接口注释）
2. 同环境存储真相（SELECT / 主键行 / 版本时间戳）
3. 同进程写路径日志（带业务 id）
4. HTTP code/msg（注意乐观更新与 200+业务失败）
5. 前端入参抓包 / 契约
6. 猜测性方言/CAST/默认值修复  ← 最后才允许
```

冲突时：**契约 + 存储 > 用户口头「应该坏了」**；口头与证据不符时，先对齐认知，再开修。

---

## E. 与既有公理衔接

| 公理（first-principles） | 本文落点 |
|--------------------------|----------|
| 证据先于宣称 | D + C2 环绿才结案 |
| Explore 先于写入 | F2 列对齐；禁幻读字段 |
| 证伪先于实现 | F1/F3：先证伪「是 Bug」 |
| 单一事实源 | 预期回流只写在行为表一处 |
| 最小有效改动 | 环绿且 F1 → **改动为零** |

行为表维度：状态机维须覆盖重入/回流。  
难 Bug 流程：见 `skills/ai-code/references/systematic-debugging.md` Phase 0 / 0.5。

---

## F. Handoff 标签（可选，便于下游）

| 标签 | 含义 |
|------|------|
| `expected_lifecycle` | 非缺陷；行为符合设计回流 |
| `env_mismatch` | 报案主键/日志环境与验证库不一致 |
| `no_write_path_log` | 声称的写操作在日志中不存在 |
| `partial_coverage` | 仅单接口验证，全链路未跑 |
| `wrong_field_observed` | 观测列/展示态与业务态不一致 |

---

## 附录：实例（非规则本身）

品牌库 `audit_status`：驳回(2) 后再 `brand/add` 同名 → 同 id 回待审(1) 为设计重新提审；测试机全链路绿；报案 id 不在测试库 + 日志仅 add 无 audit → 假阳性 F1+F3+F4。  
规则适用一切「状态回流 / 环境错位 / 未写库却抱怨状态」案件，不限于审核。

---
<!-- was skill-encoding.md -->

# skill-encoding · AI读skill/ref专用;人类可忽略
## 最优语法(实测+tokenizer,非汇编/非base64/非加密)
格式:管道行 DSL `键|键|键` 或 `P01|症状|根因|做法|禁`
语言:业务闸门中文(对账证伪本期做);字面量英文保留(cmd路径API字段grep模式错误原文)
禁:自造缩写cfg impl req(词片不省token);箭头→(单token无收益);emoji替文字(用禁/须)
禁:长散文|重复lex|与常驻规则双写|正文嵌长SQL/Java(→ref或一行形态词)
可用:数字编号P/I/L/W|枚举enum字面|grep/SELECT模板一行|STOP管道
结构:frontmatter≤2行;正文无##堆叠;单文件标题一行#可选
ref:正文=索引+路由;细节references/;hit单读一条;通用保留见下
厚薄:SKILL≤120行|私有→ref/pitfalls|handoff字段→shared/handoff-schema.yaml
通用必留:P号|报错原文|COUNT标签|矩阵读法|契约字面量|宣称↔证据对|五红线|handoff-schema字段名
## 何时用何格式
管道行:闸门G|陷阱P|路由|STOP|自检清单
紧凑表:多列对照用 `列|列` 行不用markdown对齐表
yaml块:仅handoff须validate_handoff.py;字段名与handoff-schema.yaml一致
代码块:仅当字符必须精确(SQL一行 cmd可复制);禁教学型多行示例
json:扁平事实;嵌套少用
## 低效勿用
汇编/十六进制/压缩编码:模型不解语义
多语言混排同概念(中英重复解释)
bullet嵌套>2层
完整PRD/plan复述(用@path)
## skill骨架模板
```
---
name:
description: trig+scope ≤1行
disable-model-invocation: true
---
trig: prio: load: axiom:
G0-Gn单行
ref:hit→path管道
STOP:管道
link:其他skill
```
## 进化
L0本仓1行pitfalls|L1重复≥2→harness/memories(/skill-meta EVOLVE)|L2跨仓≥3→ref/SKILL经skill-meta|禁一例升STOP
