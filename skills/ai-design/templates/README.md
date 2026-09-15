# 模板库

> 拷过去就能用的图文档模板。**复制 → 替换尖括号内容 → 渲染**，不需要从零想结构。

## 怎么用

```bash
# 1. 拷一个模板到你的项目
cp <skill>/templates/design.md  <你的项目>/docs/diagram/design.md

# 2. 改掉 <尖括号> 里的内容，图块里换成你自己的节点和边

# 3. 渲染 + 出查看页（横竖 / 主题可切换）
node <skill>/scripts/render.mjs docs/diagram/
node <skill>/scripts/viewer.mjs docs/diagram/design.md
```

## 有哪些

| 文件 | 用途 | 图型 |
|------|------|------|
| `design.md` | **主模板** —— 完整技术文档骨架：1 张架构图 + 分层/工件链/风险/未知/验收 表格 + `design_to_code` YAML | `architecture-beta` |
| `architecture.md` | 分层架构 / 服务拓扑 | `architecture-beta` |
| `flowchart.md` | 业务流程 / 决策分支 / 数据流 | `flowchart` |
| `sequence.md` | 调用时序 / 请求-响应链 | `sequenceDiagram` |
| `state.md` | 状态机 / 生命周期 | `stateDiagram-v2` |
| `er.md` | 数据模型 / 表关系 | `erDiagram` |

选型拿不准 → `references/router.md` 的决策树。

## 三条铁律（模板已经帮你守住了）

1. **一个技术文档 = 一张图**。`render.mjs` 默认只渲 `.md` 的第一个图块，多写的会被忽略。
2. **风险、决策、验收是清单 → 用表格，不出图**。
3. **图源是唯一真源**。只改 `.md` 里的图块，`assets/*.svg` 全部可重建，别手工编辑。

## 怎么补充新模板

这份模板库是**共用资产**，欢迎直接加：

1. 在 `templates/` 下新建 `<名字>.md`
2. 结构照抄现有模板：`# 标题` → `> 一句话` → `![](assets/x.svg)` → 一个 `mermaid` 代码块 → `## 说明` → `## 未知 / 待确认`
3. 图里必须用上视觉基线：语义色 `classDef`、图标/emoji 前缀、双行标签 `标题<br/>副标题`
4. 自测：`node scripts/render.mjs templates/` 必须全部渲染成功
5. 在本文件的「有哪些」表里加一行

**别加的东西**：需要新依赖的图引擎（D2 已因中文不可用而下线，见 `references/decisions.md` 决策 8）、单文件超过 25 个节点的巨型图、纯文字无图的"模板"。
