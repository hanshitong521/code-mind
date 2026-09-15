# 调用时序图

> 一次完整的「需求 → 图 → 码」调用链，谁在第几步找谁。

![调用时序图](assets/sequence.svg)

```mermaid
sequenceDiagram
  autonumber
  actor U as 👤 用户
  participant RM as 📝 ai-requirement
  participant DM as 🎨 ai-design<br/>(DiagramMind)
  participant FS as 💾 文件系统
  participant RD as 🖼️ mmdc + Chrome
  participant C as 🔧 ai-code

  U->>RM: 提出需求
  RM->>FS: 写 .requirementmind/*.json
  RM-->>U: 批量追问 frontier
  U-->>RM: 回答
  Note over RM: freeze → Requirement Gate 判定
  RM-->>DM: Gate READY（WHAT 已冻）
  DM->>FS: 读代码 / 文档取证
  Note over DM: 提节点+边 → 选图型 → 标未知
  DM->>RD: 提交 .mmd 源码
  RD-->>DM: 返回 SVG
  DM->>FS: 写 docs/diagram/design.md + assets/design.svg
  DM-->>C: 设计层产物 + drift 基线
  C->>FS: 最小 diff + LOCAL SELF-CHECK
  C-->>U: Change Manifest
```

## 说明

- **只有 RM 会问用户**：DiagramMind 与 ai-code 都不问 WHAT（FROZEN 已钉），只做取证与实现。
- **渲染是同步阻塞的**：渲染失败必须回到设计，不允许"只输出源码"蒙混。
- **渲染走 mmdc + 系统 Chrome**：一次 Chrome 启动渲染整批图，源未变则增量跳过（见 `references/render.md`）。
- **产物全部落盘**：不依赖聊天历史，任何一步中断都可从文件恢复。

## 未知项

| # | 问题 | 状态 | 需要 |
|---|------|------|------|
| 1 | ai-code 是否强制消费设计层产物 | 待确认 | 查 `ai-code/SKILL.md` G0 |

## 证据

| 步骤 | 来源 |
|------|------|
| RM 批量追问 | `ai-requirement/SKILL.md` Phase 3 |
| Gate READY | `ai-requirement/SKILL.md` Phase 7 |
| 渲染调用 | `ai-design/scripts/render.mjs`（单 Chrome 批量 + 增量） |
