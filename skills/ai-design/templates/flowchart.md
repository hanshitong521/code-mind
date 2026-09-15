# <流程名>

> 业务上怎么跑（不是代码怎么跑）。<一句话说清起点和终点。>

![业务流程图](assets/flowchart.svg)

```mermaid
flowchart TD
  Start(["👤 〔起点〕"]):::actor --> Check{"🚦 〔判据〕?"}:::decision
  Check -->|"✅ 通过"| Step["⚙️ 〔处理步骤〕"]:::step
  Check -->|"⛔ 不通过"| Fail["🚫 〔失败处置〕"]:::fail
  Step --> Store[("💾 〔落盘〕")]:::store
  Store --> Ext(("🌐 〔外部系统〕")):::ext
  Ext --> End(["📦 〔终点〕"]):::done

  classDef actor fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef decision fill:#fdf2e0,stroke:#dda94f,color:#5c3c07,stroke-width:1.5px
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
  classDef store fill:#f2eafd,stroke:#a184d6,color:#3a2159,stroke-width:1.5px
  classDef ext fill:#e6f6f6,stroke:#5aa8a8,color:#144545,stroke-width:1.5px
  classDef fail fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef done fill:#e6f6ec,stroke:#5aa877,color:#14452a,stroke-width:1.5px
```

## 说明

- **入口条件**：〔什么情况下会走到这条流程〕
- **回流环**：〔哪几步可能退回，退回的判据是什么〕
- **终止条件**：〔什么状态算真的结束〕

## 失败路径

| # | 触发 | 处置 | 残留风险 |
|---|------|------|----------|
| 1 | 〔触发条件〕 | 〔怎么收场〕 | 〔有没有脏数据 / 需要人工〕 |

## 未知 / 待确认

| # | 问题 | 状态 | 需要 |
|---|------|------|------|
| 1 | 〔问题〕 | 未知 | 〔查什么〕 |

---

<!-- 图型要点
  · 首行写 flowchart TD（竖排）或 LR（横排）；viewer.mjs 支持一键切换
  · 形状语义：(["角色/起止"]) [(存储)] {"判断"} (("外部")) ["步骤"]
  · 双行标签用 <br/>（这是允许的），但别放 <尖括号> 文字 —— htmlLabels 会吃掉它
  · 占位统一用 〔〕
  · 节点超 25 个 → 拆文档
  · 边一律标语义：A -->|"调用"| B
-->
