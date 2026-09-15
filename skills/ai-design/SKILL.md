---
name: diagram-mind
version: 6.6.0
description: >-
  DiagramMind — 把需求/代码/文档变成一张看得懂的系统图。分析模块·数据流·角色 → 选图型 → 写 Mermaid → 预检 →
  渲染 + 构图审计 + drift。Triggers: /ai-design, /diagram, DiagramMind, 画图, 架构图, 流程图, 时序图.
disable-model-invocation: true
---

trig:/ai-design|/diagram|DiagramMind|画图|架构图|流程图|时序图 prio:rules>this
load:本页;references/ 命中单读 禁批读;禁读 evals|reports|assets
axiom:构图>配色 | 图>表>文字 | 一文一图 | 主链不删·其余进表 | 图说人话·证据进表 | 无证据不画 | 未知标 UNKNOWN | 先预检再渲染
ssot:../../shared/core.md 构图:references/layout.md ponytail:裁scope

# DiagramMind v6.6（路由器）

**不是画图工具，是项目理解系统。** 文字只做补充；核心内容必须一张图看懂 —— **看得懂的前提是图上东西够少**。

## 三条硬规则

### 1. 图说人话，证据进表

图给产品/运维/老板看，代码证据给开发查。**节点标签只写业务动作、角色、结果。**

| 载体 | 写什么 | 禁止 |
|------|--------|------|
| 图节点/边 | 中文业务话 + 可选 emoji | 类名、方法名、`path:line`、URL、SQL |
| §0 节点证据表 | `path:line`、日志、需求原话 | 复述整张图 |
| 工件链 / YAML | 代码落点、模块、接口 | 空间拓扑 |

### 2. 一张图 = 一条主链 + 挂在链上的锚点

图只回答两件事：**怎么跑的、卡在哪。** 数字明细、排除项、对策清单**本来就是表格的内容**，再画一遍是图变丑的头号原因。

| 图层 | 进图条件 | 数量 |
|------|---------|------|
| 主链（业务流程） | 几乎总是（硬要求） | 逐步箭头一步不删，≤8 步 |
| 症状 / 瓶颈锚点 | 已定位 | 挂出事那一步**旁边**，≤2 |
| 对策 | 默认不进图 | 要进 ≤3 条，**不另开 subgraph 堆清单** |
| 数字明细 / 排除项 | **不进图** | 回 §关键数字 / §排查脉络 |

**构图预算（超了就是白画）**：节点 ≤12 · 边 ≤14 · 画布宽 320~1200px · 宽高比 0.32~2.6 · 填充率 ≥12% · 单行 ≤26 字。
超标第一动作是**砍信息进表**，不是换主题、不是放大画布。细则 `references/layout.md`。

### 3. 按需加注，不凑字段

有依据才写数字/排查态/对策目标；无方案节就删 §解决方案。**D0 必写 3 行**（不进图）：读者三问 · 输入类型 · 选用标注。
节点副标题最多 1~2 个关键事实，明细进表。细则 `references/annotation.md`。

## 流水线（D0→D7）

```
D0 判定 → D1 分析 → D2 选图型+定构图 → D3 写 DSL + 预检 → D4 标未知+风险 → D5 渲染+审计 → D6 drift → D7 交付
```

| 步 | 动作 | 出口 |
|----|------|------|
| D0 | 判输入类型 → **读者三问 + 选用标注** | 分析范围 + 标注菜单 |
| D1 | 提节点+边，**每项带证据** | 节点表 / 边表 |
| D2 | 按 `router.md` 选图型；按 `layout.md` 定方向与锚点（默认「垂直主链 + 侧挂锚点」） | 图型 + 构图 1 行 |
| D3 | 按 `mermaid.md` 写 DSL → **`node scripts/lint.mjs` 预检，不绿不许渲染** | .mmd 全绿 |
| D4 | 未知→`UNKNOWN` 节点；风险→**表格** | 未知清单 |
| D5 | `node scripts/render.mjs <目录> --strict` | SVG + 审计全绿 |
| D6 | `node scripts/drift.mjs` 代码 vs 图 | OK / FAIL |
| D7 | 有代码变更 → 更新 `docs/diagram/design.md`（**同一份文档**，不新开图） | 交 `/ai-code` |

## 图型路由（细则 `references/router.md`）

业务/数据/Agent 流程·系统总览 → `flowchart` ｜ 调用链·接口时序 → `sequenceDiagram` ｜ 状态机 → `stateDiagram-v2`
实体关系 → `erDiagram` ｜ **分层架构·谁依赖谁（首选，自带图标）** → `architecture-beta`
产品草图/架构评审/Java 调用链 → Excalidraw / Draw.io / PlantUML（V2 占位，只出 DSL 不渲）

## 写图规则（细则 `references/mermaid.md`）

必须：含**业务主链** ｜ 标签**人话** ｜ 证据进 §0 ｜ 按需加注 ｜ 对得上预算 ｜ 边标动词 ｜ UNKNOWN ｜ 风险→表 ｜ **预检全绿 + 渲染成功 + 审计全绿**才算交付

视觉基线（不达标就是白画）：走 `assets/mermaid-theme*.json` ｜ 双行标签 `标题<br/>副标题` ｜ `classDef` **只给关键节点** ｜ 架构图用 `architecture-beta` 内置图标 ｜ `flowchart` 用 `curve: basis` ｜ 长链走 `LR`

禁止：❌ 虚构模块 ｜ ❌ **图里写类名/路径/行号/URL** ｜ ❌ 无图纯文字解释 ｜ ❌ 巨型图（>12 节点、>14 边必砍） ｜ ❌ 画布宽 >1200 ｜ ❌ 猜数据来源 ｜ ❌ 图码不符不标注 ｜ ❌ 一文档多图 ｜ ❌ 把三张表内容再画进图 ｜ ❌ **未过 `lint.mjs` 就渲染**

**未知与风险**（`unknowns-risks.md`）：不确定**不许猜** —— 图内画 `UNKNOWN` 节点 + 清单（状态 / 需要查什么）；风险**用表格**，不单独出图。

## 输出规范（`references/output-spec.md`）

**一个技术文档 = 一张图**，硬约束。起手直接拷 `templates/design.md`，别从零写。

```
docs/diagram/
├── design.md           1 张图 + 分层/工件链/风险/未知/验收 表 + design_to_code YAML
├── design.viewer.html  查看页（自包含，横竖 + 主题 + 缩放可切）
└── assets/             design.svg（主产物）+ variants/（4 组合）
```

多主题 → **拆成多份文档**，每份各一张图。`design.md` 一文件双职：给人 30 秒看懂，给 `/ai-code` 结构化交接（`design-delivery.md`）。

## 命令

```bash
node scripts/lint.mjs   docs/diagram/            # ① 预检：零依赖·毫秒级·不启 Chrome（写 DSL 后立刻跑）
node scripts/render.mjs docs/diagram/ --strict   # ② 渲染：单 Chrome 批量 + 未变跳过 + 构图审计
node scripts/render.mjs docs/diagram/ --variants #    额外出 主题×方向 4 组合
node scripts/render.mjs --check                  #    探测工具链
node scripts/viewer.mjs docs/diagram/design.md   # ③ 查看页
node scripts/drift.mjs  <项目根> docs/diagram    # ④ 代码 vs 图
node scripts/selftest.mjs                        # 自测（含 lint 用例）
node scripts/preview.mjs  docs/diagram/design.md # 救急：没工具链时出「打开即出图」的单文件 HTML
```

| render 选项 | 作用 |
|------|------|
| `--theme light\|dark\|none` | 主题，默认 light |
| `--direction tb\|lr` | 强制方向（**只对 flowchart 生效**） |
| `--layout auto\|dagre\|elk` | auto（默认）= dagre 不达标才试 elk，**且只针对布局类违规**（宽/比例/留白/孤岛）；节点·边·标签超量是内容问题，换引擎救不了 → 跳过复算 |
| `--strict` / `--no-audit` / `--variants` / `--force` / `--all-blocks` / `--json` | 审计超标即退出 1 / 关审计 / 出变体 / 忽略缓存 / 一文多图 / 机器可读 |

**提速要点**：先 `lint` 再 `render`——把「渲染 → 审计失败 → 猜原因 → 改 → 重渲」的多轮压成一轮。审计不过时 render 会**自动附 lint 原因**，直接照着改。
`preview.mjs` 是**救急预览**（浏览器从 CDN 拉 mermaid 渲染，需联网、不做构图审计）；**正式交付物一律走 `render.mjs --strict`**。
`.md` 是唯一真源，`assets/**` 全可重建。工具链装到项目 `.tools/diagram`。

## 模板（`templates/`）

拷贝即用：`design.md`（主）· `architecture.md` · `flowchart.md` · `sequence.md` · `state.md` · `er.md`。
占位符统一 `〔...〕`；**图块里除 `<br/>`/`<span>` 外不能用尖括号**（`htmlLabels` 会当 HTML 吃掉）。

## drift 检测（细则 `references/drift.md`）

代码新增模块 vs 图 → OK / FAIL + 差异。

ref:构图→`layout.md`｜加注→`annotation.md`｜DSL→`mermaid.md`｜图型→`router.md`｜渲染→`render.md`｜预检→`scripts/lint.mjs`｜未知风险→`unknowns-risks.md`｜输出→`output-spec.md`｜D7→`design-delivery.md`｜模板→`templates/`｜范例→`evals/samples/`｜栈→`../../shared/core.md`
STOP:删主链只留结论|无证据画节点|猜未知|编数字|巨型图|节点>12不砍|画布宽>1200|无图文字解释|ref批读|图块写尖括号|图里写类名路径行号|一文档多图|为风险单开图|三张表内容进图|带间连边|对策单开subgraph|空节占位|有代码变更不出design.md|design.md YAML未过validate_handoff|lint未绿就渲染
lex:图型路由 构图 预算 主链 锚点 节点 边 证据 说人话 按需加注 D0 节点证据表 UNKNOWN 风险表 drift 一文一图 主题 视觉基线 渲染 审计 预检 lint 变体 查看页 模板 设计交付
