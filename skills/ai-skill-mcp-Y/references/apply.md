# 改配方（一次一资源）

## 通用纪律

- 一次只改一个资源；改完**必须**复跑 `skillmind.py audit` + 该资源的 trigger 四类。
- 任何 skill 改动后跑 `skillmind.py selftest`（24 项端到端，零污染）与
  `python3 scripts/validate_bundle.py`。
- 动了 skill 内容 → `skillmind.py registry build` 重算哈希；若该 skill 在
  `shared/release-manifest.yaml` 里声明，须同步 `content_hash`（否则 `verify` 报 DRIFT）。
- 版本号递增并写 `VERSION` / `skill.yaml`；`skill.yaml` 必须过 `manifest validate`。

## Skill OPTIMIZE / SPLIT

description 只答「现在要不要加载我?」≤1 行；含 **Use when** + **Not for**。
禁：工作流摘要、一碰领域就触发（「数据库相关」）。

根 `SKILL.md` 只留：frontmatter · 何时用/不用 · 命令/路由 · 不可破 invariant · 输出契约。
移出：API 长文、全场景步骤、重复示例、项目业务规则副本、AGENTS 已有事实。

尺寸：高频常驻根 <200 words；普通根 <500 words；>800 words**强制**拆 `references/`。
**行数与 words 是两套判据**：根 `SKILL.md` 另有 **120 行硬顶**（所有 skill，不限常驻）。
L2 单条 reference 另有 **2000 tokens 预算**（`_common.est_tokens` 口径；超 2× 即必须拆）。
且路由表写清「命中才读哪一条」。
禁为拆而拆：一次任务要读 ≥5 个碎文件 = 失败，合回去。

`audit` 报尺寸问题先分清责任：**词数超** → 常驻/加载成本；**行数超** → 结构已碎。
两者都可能同时命中同一文件，属正常（同一份文档两个维度各超各的）。

强模型：删 18 步食谱、泛 MUST/ALWAYS；改成 Goal / Constraints / DoD / Evidence。
弱模型仍要跑通时：细节放 reference，根不写行程。

冲突：留一个赢家，输家 description 改 Deprecated 指向赢家；90 天后再评估删除。
低频 ≠ 可删：灾备 / 事故 / 迁移 / 安全 → KEEP。

机械审计的 verdict 只由**可执行动作**决定（`action != KEEP`）：
`BLOCK` > `OPTIMIZE`（有 OPTIMIZE/SPLIT/MERGE/LAZY-LOAD/DISABLE-CANDIDATE） > `PASS`（全 KEEP）。
KEEP 是「无需动作」的结论，**不**计入 findings —— 否则审计永远报 OPTIMIZE（报警失效）。
`payload.actionable` 即该判定用的可执行条数。

审计报 `triggers.exclude 为空` 时先分清责任：若 description 写了 `Not for …` 却仍为空，
是**解析器**没派生（`_common.derive_excludes`），不是作者漏写 —— 别去改 description。

骨架（V2 版，见 `templates/skill-skeleton/`）：

```
---
name:
version: x.y.z
description: Use when <精确场景>. Not for <易误触发邻域>.
---
trig:<词>| <词> prio: load:本页 ref命中单读
axiom:<一句话公理>
G0-Gn 单行
ref:命中→path
STOP:管道
```

## 新增 Skill（V2 必做）

1. 复制 `templates/skill-skeleton/` → `skills/<new>/`
2. 替换 `<SKILL_NAME>` / `<TRIGGER>` / `<STOP_LIST>` 等占位符
3. 写 `skill.yaml`（字段见 `spec-v2.md §17`），过 `manifest validate`
4. `tests/` 放 trigger 四类用例；`benchmarks/` 挂 ≥1 条真实任务基线
5. `registry build` → 确认新 skill 出现在注册表且 `hash` 自洽

## MCP OPTIMIZE

目标：全量目录 → 域发现 → 本任务最小充分集（常见 3–8，**非硬顶**）。
分层：Core 只读 · Domain · Write/破坏（明确写意图） · Deep 默认藏。
schema：让模型选对工具 + 对参数；删同义 tool、过宽参数、一段里做 5 件事。
standing 白名单写进 AGENTS/L0；其余 on-demand。
结果大：handle/摘要，禁把 10MB 日志塞上下文。
retry/timeout/queue 有界；多 Agent 禁重复冷启动同一 daemon（防 5×3=15× 重试风暴）。
预算依据：`shared/capability-registry.yaml` 的 `tool_budget.default_max_tools_per_phase`。

## AGENTS / rules OPTIMIZE

必读清单 → 导航地图（场景→文件，否则不加载）。
删：写高质量代码 / 认真思考 / 每次编辑前读三份 doc / 每次全量测试。
留：栈、目录真源、prod 禁写、项目公式、模型猜不到的枚举。
`alwaysApply` 只留 L0 事实；其余 globs 或 skill。
完成条件：Goal · Constraints · DoD · Evidence；本地测试许可写清，勿逐步请示。

## 验证（改完必做）

1. 对该资源复跑 trigger 4 类（`references/trigger-tests.md`）；Hard Gate 任一 FAIL 则回滚。
2. `skillmind.py selftest` 全绿。
3. 口头走一遍 1 个 positive 任务：「会不会误加载 / 会不会找不到」。
4. 宣称省 token 必须同时报：**是否还能选对 skill** + **P0 证据是否还在**。
   禁只报压缩率。
