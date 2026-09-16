---
name: diagram-mind
version: 6.6.0
description: >-
  DiagramMind — 把需求/源码/文档变成一张看得懂的系统图。分析模块·数据流·角色 → 选图型 → 写 Mermaid → 预检 →
  渲染 + 构图审计 + drift。Triggers: /ai-design, /diagram, DiagramMind, 画图, 架构图, 流程图, 时序图.
disable-model-invocation: true
---

trig:/ai-design|/diagram|DiagramMind|画图|架构图|流程图|时序图 prio:rules>this
load:本页;references/ 命中单读 禁批读;禁读 evals|reports|assets
axiom:构图>配色 | 图>表>文字 | 一文一图 | 主链不删·其余进表 | 图说人话·证据进表 | 无证据不画 | 未知标 UNKNOWN | 先预检再渲染
ssot:../../shared/core.md 构图:references/layout.md ponytail:裁scope

# DiagramMind v6.6（路由器）

**不是画图工具，是项目理解系统。** 文字只做补充；核心内容必须一张图看懂 —— **看得懂的前提是图上东西够少**。

**何时用**：把需求 / 源码 / 文档 / 事故变成一张人话系统图；或给 `/ai-code` 出设计交付（`docs/diagram/design.md`）。
**何时不用**：写业务码（`/ai-code`）｜澄清 WHAT（`/ai-requirement`）｜日志排障与财务核对（非本技能职责）。

## 三条硬规则（不可破 invariant）

1. **图说人话，证据进表**：图节点/边只写中文业务动作·角色·结果（可选 emoji）；**禁**类名、方法名、`path:line`、URL、SQL。代码证据 → §0 节点证据表；代码落点 → 工件链 / YAML。细则 `annotation.md` · `mermaid.md`。
2. **一图 = 一条主链 + 挂在链上的锚点**：主链逐步箭头**一步不删**、≤8 步；症状/瓶颈锚点 ≤2、挂出事那一步**旁边**；对策**默认不进图**（要进 ≤3 条，**不另开 subgraph 堆清单**）；数字明细/排除项**不进图** → 回 §关键数字 / §排查脉络。预算：节点 ≤12 · 边 ≤14 · 画布宽 320~1200px · 宽高比 0.32~2.6 · 填充率 ≥12% · 单行 ≤26 字；**超标第一动作是砍信息进表**，不是换主题、不是放大画布。细则 `layout.md`。
3. **按需加注，不凑字段**：有依据才写数字 / 排查态 / 对策目标；无方案节就删 §解决方案。**D0 必写 3 行**（读者三问 · 输入类型 · 选用标注，不进图）；节点副标题最多 1~2 个关键事实。细则 `annotation.md`。

**未知与风险**：不确定**不许猜** —— 图内 `UNKNOWN` 虚线节点 + 未知清单（状态 / 需要查什么）；风险**用表格**，不单独出图。细则 `unknowns-risks.md`。

## 流水线路由（D0→D7；命中才读对应 reference，禁批读）

```
D0 判定 → D1 分析 → D2 选图型+定构图 → D3 写 DSL + 预检 → D4 标未知+风险 → D5 渲染+审计 → D6 drift → D7 交付
```

| 步 | 动作 | 出口 | 读 |
|----|------|------|----|
| D0 | 判输入类型 → **读者三问 + 选用标注** | 分析范围 + 标注菜单 | `analysis.md` · `annotation.md` |
| D1 | 提节点 + 边，**每项带证据** | 节点表 / 边表 | `analysis.md` |
| D2 | 选图型；定方向与锚点（默认「**垂直主链 + 侧挂锚点**」） | 图型 + 构图 1 行 | `router.md` · `layout.md` |
| D3 | 写 DSL → **`node scripts/lint.mjs` 预检，不绿不许渲染** | .mmd 全绿 | `mermaid.md` · `render.md` |
| D4 | 未知 → `UNKNOWN` 节点；风险 → **表格** | 未知清单 | `unknowns-risks.md` |
| D5 | `node scripts/render.mjs <目录> --strict` | SVG + 审计全绿 | `render.md` |
| D6 | `node scripts/drift.mjs` 代码 vs 图 | OK / FAIL | `drift.md` |
| D7 | 有代码变更 → 更新 `docs/diagram/design.md`（**同一份文档**，不新开图） | 交 `/ai-code` | `design-delivery.md` |

**图型路由**：业务/数据/Agent 流程·系统总览 → `flowchart` ｜ 调用链·接口时序 → `sequenceDiagram` ｜ 状态机 → `stateDiagram-v2` ｜ 实体关系 → `erDiagram` ｜ **分层架构·谁依赖谁（首选，自带图标）** → `architecture-beta` ｜ 产品草图/架构评审/Java 调用链 → Excalidraw / Draw.io / PlantUML（**V2 占位，只出 DSL 不渲**）。细则 `router.md`。

## 最小输出契约

**一个技术文档 = 一张图**（硬约束）；多主题 → 拆多份文档，每份各一张图。起手直接拷 `templates/design.md`。
产物固定落 `docs/diagram/`：`design.md`（图源 + 表格 + `design_to_code` YAML，**唯一真源**）· `design.viewer.html` · `assets/`（`design.svg` + `variants/`，**全可重建，禁手改**）。目录树 / 模板 / 分工 / 反模式 → `output-spec.md`。

**交付闸门**：含业务主链 ｜ 标签人话 ｜ 证据进 §0 ｜ 对得上预算 ｜ 边标动词 ｜ UNKNOWN ｜ 风险进表 ｜ **`lint.mjs` 全绿 + `render.mjs --strict` 全绿**才算交付。
**视觉基线**（走主题 JSON · 双行标签 · `classDef` 只给关键节点 · `architecture-beta` 内置图标 · `curve: basis` · 长链走 `LR`）→ `toolchain.md`。

ref:图型→`router.md`｜构图/预算→`layout.md`｜加注→`annotation.md`｜DSL→`mermaid.md`｜分析取证→`analysis.md`｜渲染/预检/审计→`render.md`｜工具链/主题/查看页→`toolchain.md`｜未知风险→`unknowns-risks.md`｜输出/模板→`output-spec.md`｜D7交付→`design-delivery.md`｜drift→`drift.md`｜ADR→`decisions.md`｜模板→`templates/`（design.md·architecture.md·flowchart.md·sequence.md·state.md·er.md）｜范例→`evals/samples/`｜栈→`../../shared/core.md`
STOP:删主链只留结论|无证据画节点|猜未知|编数字|巨型图|节点>12不砍|画布宽>1200|无图文字解释|ref批读|图块写尖括号|图里写类名路径行号|一文档多图|为风险单开图|三张表内容进图|带间连边|对策单开subgraph|空节占位|有代码变更不出design.md|design.md YAML未过validate_handoff|lint未绿就渲染
lex:图型路由 构图 预算 主链 锚点 节点 边 证据 说人话 按需加注 D0 节点证据表 UNKNOWN 风险表 drift 一文一图 主题 视觉基线 渲染 审计 预检 lint 变体 查看页 模板 设计交付
