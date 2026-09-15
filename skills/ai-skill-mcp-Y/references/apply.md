# 改配方（一次一资源）

## Skill OPTIMIZE / SPLIT

description 只答「现在要不要加载我?」≤1行; 含 **use when** + **not for**。
禁: 工作流摘要、一碰领域就触发(「数据库相关」)。

根 SKILL.md 只留: frontmatter · 何时用/不用 · 路由 · 不可破 invariant · 输出契约。
移出: API 长文、全场景步骤、重复示例、项目业务规则副本、AGENTS 已有事实。

尺寸: 高频根 <200 words; 普通 <500; >800 强制拆 `references/` 且路由表写清「命中才读哪一条」。
禁为拆而拆: 每次任务要读 ≥5 个碎文件 = 失败, 合回去。

强模型: 删 18 步食谱、泛 MUST/ALWAYS; 改成 Goal/Constraints/DoD/Evidence。
弱模型仍要跑通时: 细节放 reference, 根不写行程。

冲突: 留一个赢家, 输家 description 改 Deprecated 指向赢家; 90 天后再删。
低频≠可删: 灾备/事故/迁移/安全 → KEEP。

骨架:

```
---
name:
description: Use when <精确场景>. Not for <易误触发邻域>.
---
trig: prio: load:本页 ref命中单读
G0-Gn 单行
ref:命中→path
STOP:管道
```

## MCP OPTIMIZE

目标: 全量目录 → 域发现 → 本任务最小充分集(常见 3–8, 非硬顶)。
分层: Core只读 · Domain · Write/破坏(明确写意图) · Deep默认藏。
schema: 让模型选对工具+对参数; 删同义 tool、过宽参数、一段里做 5 件事。
standing 白名单写进 AGENTS/L0; 其余 on-demand。
结果大: handle/摘要, 禁把 10MB 日志塞上下文。
retry/timeout/queue 有界; 多 Agent 禁重复冷启动同一 daemon。

## AGENTS / rules OPTIMIZE

必读清单 → 导航地图(场景→文件, 否则不加载)。
删: 写高质量代码/认真思考/每次编辑前读三份 doc/每次全量测试。
留: 栈、目录真源、prod 禁写、项目公式、模型猜不到的枚举。
alwaysApply 只留 L0 事实; 其余 globs 或 skill。
完成: Goal · Constraints · DoD · Evidence; 本地测试许可写清, 勿逐步请示。

## 验证（改完必做）

对该资源复跑 trigger 4类; Hard Gate; 给 1 个 positive 任务口头走一遍「会不会误加载」。
宣称省 token 必须同时报: 是否还能选对 skill、P0 证据是否还在。
