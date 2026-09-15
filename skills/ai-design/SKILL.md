---
name: diagram-mind
version: 6.5.0
description: >-
  DiagramMind — 把需求/代码/文档变成系统理解图。自动分析模块·数据流·角色 → 选图型 →
  生成 Mermaid（flowchart/sequence/state/er/architecture-beta）→ 标未知与风险 → 渲染出图 + 构图审计 + drift 检测。Triggers: /ai-design, /diagram,
  DiagramMind, 画图, 架构图, 流程图, 时序图.
disable-model-invocation: true
---

trig:/ai-design|/diagram|DiagramMind|画图|架构图|流程图|时序图 prio:rules>this load:本页 ref命中单读 禁ref批
axiom:构图预算>配色 | 图>流程>表格>文字 | 一文一图 | 主链不可删·其余进表 | 图说人话证据进表 | 按需加注不凑字段 | 无证据不画节点 | 未知显式标记禁猜 | 先分析再画 | 渲染过+审计过才算出图
ssot:../../shared/core.md 构图:references/layout.md ponytail:裁scope

# DiagramMind v6.5（路由器）

**不是画图工具，是项目理解系统。** 文字只做补充/解释/记录决策；核心内容必须一张图看懂 —— **看得懂的前提是图上东西够少**。

## 三条硬规则

### 1. 图说人话，证据进表

**图给产品/运维/老板看；代码证据给开发/Agent 查。** 禁止类名、`path:line` 进节点标签。

| 载体 | 写什么 | 禁止写什么 |
|------|--------|-----------|
| **图节点/边** | 业务动作、角色、结果（中文 + 可选 emoji） | 类名、方法名、`path:line`、Feign 路径 |
| **§0 节点证据** | `path:line`、日志、需求原话 | 复述整张图 |
| **工件链 / YAML** | 代码落点、模块、接口 | 空间拓扑 |

### 2. 一张图 = 一条主链 + 挂在链上的锚点

**图只回答两件事：怎么跑的、卡在哪。** 排查结论、数字明细、排除项、对策清单**都不是流程** —— 它们本来就是 §关键数字 / §排查脉络 / §解决方案 三张表的内容，再画一遍是重复劳动，也正是图变难看的头号原因。

| 图层 | 进图条件 | 图上放多少 |
|------|---------|-----------|
| **主链**（业务流程） | 几乎总是（硬要求） | 触发 → 判断 → 处理 → 外呼 → 落库/等待，**逐步箭头，一步不删**；≤8 步 |
| **症状 / 瓶颈锚点** | 已定位 | 挂在出事那一步的**旁边**，≤2 个 |
| **对策** | **默认不进图** | 要进就 ≤3 条、挂在对应瓶颈旁；**不另开「对策 subgraph」堆清单** |
| 数字明细 / 排除项 | **不进图** | 回 §关键数字 / §排查脉络 |

**构图预算（超了就是白画）**：节点 ≤12 · 边 ≤14 · **画布宽 320~1200px** · 宽高比 0.32~2.6 · 填充率 ≥12% · 单行标签 ≤26 字。
细则与实测依据 `references/layout.md`。**超标的第一动作是砍信息进表**，不是换主题、不是放大画布。
`node scripts/render.mjs <目录> --strict` 出图后自动体检，不达标直接非零退出。

**不许**用「只剩结论框」代替流程。

### 3. 按需加注，不凑字段

细则 `references/annotation.md`。数字、排查态、对策目标 —— **有依据才写**；无方案节就删 §解决方案。

**D0 必写 3 行**（不进图）：读者三问 · 输入类型 · 选用标注（0~N）。
节点副标题最多 1～2 个关键事实；明细进表。

## 流水线（D0→D7）

```
D0 输入判定 → D1 分析(模块/数据流/角色) → D2 选图型+定构图 → D3 生成 DSL → D4 标未知+风险 → D5 渲染+构图审计 → D6 drift 检测 → D7 设计交付
```

| 步 | 动作 | 出口 |
|----|------|------|
| D0 | 判输入类型 → **读者三问 + 选用标注**（`annotation.md`） | 分析范围 + 标注菜单勾选 |
| D1 | 提节点+边，**每项带证据** | 节点表 / 边表 |
| D2 | 按 `references/router.md` 选引擎+图型；按 `references/layout.md` **定方向与锚点位置**（默认「垂直主链 + 侧挂锚点」），先对预算（≤12 节点） | 引擎+图型+构图 1 行 |
| D3 | 按 `references/mermaid.md` 生成 DSL | .mmd |
| D4 | 未知→UNKNOWN 节点；风险→**表格**（不单独出图） | 未知清单 |
| D5 | `node scripts/render.mjs <目录> --strict`（单 Chrome 批量 + 未变跳过 + 构图审计 + ELK A/B） | SVG/PNG + 审计全绿 |
| D6 | `node scripts/drift.mjs` 代码 vs 图 | OK / FAIL |
| D7 | 有代码变更 → 更新 `docs/diagram/design.md`（**同一份技术文档**，不新开图） | 交给 `/ai-code` |

## 图型路由（细则 `references/router.md`）

| 场景 | 引擎·图型 |
|------|-----------|
| 业务/数据/Agent 流程、系统总览 | Mermaid `flowchart` |
| 调用链、接口时序 | Mermaid `sequenceDiagram` |
| 状态机、生命周期 | Mermaid `stateDiagram-v2` |
| 实体关系、数据模型 | Mermaid `erDiagram` |
| **分层架构、谁依赖谁（首选，自带图标）** | Mermaid **`architecture-beta`** |
| 产品讨论草图 | Excalidraw（V2 占位） |
| 架构评审 / PPT 交付 | Draw.io（V2 占位） |
| Java 调用链 | PlantUML（V2 占位） |
| 需嵌套容器的超复杂架构 | D2（**V2 占位**，v6.1 已下线） |

## 生成规则（细则 `references/mermaid.md`）

必须：图含**业务流程主链**｜标签**人话**｜证据进 §0｜按需加注｜节点/边/带**对得上预算**｜边标动词｜UNKNOWN｜风险→表｜**渲染成功 + 审计全绿**才算交付

**视觉基线**（不达标就是白画）：走 `assets/mermaid-theme*.json` 主题（中文无衬线 + 柔和配色 + 三级字阶）｜节点标签双行 `标题<br/>副标题`｜语义色 `classDef` **只给关键节点**（症状/瓶颈/对策/排除项）｜图标前缀（架构图用 `architecture-beta` 内置 `cloud/server/database/internet`）｜`flowchart` 用 `curve: basis`｜长链走 `LR`。完整配方 `references/layout.md`。

禁止：❌ 虚构模块 ｜ ❌ **图里写 Java/路径/行号** ｜ ❌ 无图直接文字解释 ｜ ❌ 巨型图（**>12 节点**、>14 边必砍）｜ ❌ 画布宽 >1200px 或 <320px ｜ ❌ 猜数据来源 ｜ ❌ 图与代码不符不标注 ｜ ❌ **一个文档塞多张图** ｜ ❌ 把 §关键数字/§排查脉络/§解决方案 的内容再画进图

## 未知与风险（细则 `references/unknowns-risks.md`）

不确定**不许猜**：图内画 `UNKNOWN` 节点 + 清单（状态 / 需要查什么）。风险**用表格**表达，不单独出图 —— 风险是清单，不是拓扑。

## 输出规范（细则 `references/output-spec.md`）

**一个技术文档 = 一张图。** 这是硬约束，不是偏好：图多了没人看，token 也白烧。

```
docs/diagram/
├── design.md           唯一技术文档 —— 1 张图 + 分层/工件链/风险/未知/验收 表格 + design_to_code YAML
├── design.viewer.html  查看页（自包含单文件，横竖 + 主题 + 缩放可切换）
└── assets/
    ├── design.svg      主产物 = light + 源方向，md 里引用的就是它
    └── variants/       --variants 产出的 4 个组合，供查看页切换
```

- 多主题 → **拆成多份文档**，每份各一张图；不要在一份文档里堆图。
- `design.md` 一文件双职：给人「30 秒看懂」，给 `/ai-code` 结构化交接。细则 `references/design-delivery.md`。
- 起手直接拷 `templates/design.md`，别从零写。

## 渲染（细则 `references/render.md`）

```bash
node scripts/render.mjs docs/diagram/                # 渲染目录 → assets/（单 Chrome 批量 + 未变跳过 + 构图审计）
node scripts/render.mjs docs/diagram/ --strict       # 审计不达标 → 退出码 1（交付前必跑）
node scripts/render.mjs docs/diagram/ --variants     # 额外出 主题×方向 变体
node scripts/render.mjs --check                      # 探测工具链（Chrome/mermaid-cli/puppeteer/elk）
node scripts/viewer.mjs docs/diagram/design.md       # 出查看页（横竖 + 主题 + 缩放可切换）
```

| 选项 | 作用 |
|------|------|
| `--theme light\|dark\|none` | 主题，默认 `light`；`none` = Mermaid 原始样式 |
| `--direction tb\|lr` | 强制流程图方向（**只对 `flowchart` 生效**，其余图型忽略并告警） |
| `--layout auto\|dagre\|elk` | 布局引擎，默认 `auto` = dagre 不达标才追加 elk 复算取优 |
| `--strict` | 构图审计有任何超标 → 退出码 1 |
| `--no-audit` | 关掉审计输出 |
| `--variants` | 产出 `主题(浅/深) × 方向(竖/横)` 网格，供查看页切换 |
| `--force` | 忽略增量缓存强制重渲（**改了主题/布局才需要**） |
| `--all-blocks` | 允许一个 `.md` 渲多个图块（**默认关**，一文档只渲第一张图） |

**审计判据**（`render.mjs` 出图后自动量，阈值同 `references/layout.md`）：画布宽≤1200 · 宽高比 0.5~2.6 · 节点≤12 · 边≤14 · 填充率≥12% · 无孤岛空档 · 单行标签≤26 字。
非 flowchart（sequence/state/er/architecture）只量画布，不算节点账。

**效率**：一次 Chrome 启动渲染全部图；源/主题/方向/布局未变则跳过（`.diagramrender.json` 记 hash）。AI 迭代循环里重复调用几乎零成本。

`.md` 是唯一真源，`assets/**` 全是可重建产物。工具链装到项目 `.tools/diagram`（国内镜像，不落 C 盘）。

## 模板（`templates/`）

**拷贝即用**：`design.md`（主模板）· `architecture.md` · `flowchart.md` · `sequence.md` · `state.md` · `er.md`。
占位符统一是 `〔...〕`；**图块里不能用 `<尖括号>`** —— `flowchart` 开了 `htmlLabels`，会被当 HTML 标签吃掉。
这是共用资产，按 `templates/README.md` 的约定直接补充新模板。

## drift 检测（细则 `references/drift.md`）

```bash
node scripts/drift.mjs <项目根> docs/diagram   # 代码新增模块 vs 图 → OK / FAIL + 差异
```

## 自测

```bash
node scripts/selftest.mjs   # 生成样例图并渲染，证明工具链可用
```

ref:构图→`references/layout.md`（方向/带/预算/ELK）｜按需加注→`references/annotation.md`｜细则→`references/*.md`（命中单读）｜起手模板→`templates/`｜D7→`references/design-delivery.md`｜范例→`evals/samples/`｜栈→`../../shared/core.md`
STOP:删业务流程只留结论|无证据画节点|猜未知|编造数字|编造对策效果|无依据凑怀疑点|巨型图|节点>12不砍|画布宽>1200|无图文字解释|ref批读|虚构模块|未渲染或审计未过就宣称出图|图代码不符不标注|一文档多图|为风险单开图|重复渲染未变的图|图块里写<尖括号>|图里写类名路径行号|空节占位|把三张表内容再画进图|带间连边|对策单开subgraph|有代码变更不出 design.md|design.md YAML 未过 validate_handoff
lex:图型路由 构图 预算 带 序号 主链 锚点 节点 边 证据 说人话 按需加注 排查态 关键数字 解决方案 D0 节点证据表 UNKNOWN 风险表 drift 一文一图 主题 视觉基线 渲染 审计 宽度 宽高比 留白 孤岛 ELK 变体 查看页 横竖切换 模板 系统地图 设计交付
