# 业务流程图

> 一条需求从进来到交付，业务上怎么跑（不是代码怎么跑）。

![业务流程图](assets/workflow.svg)

```mermaid
flowchart TD
  Start(["👤 用户提出需求"]):::actor --> Route{"需求清楚吗<br/>单一解读?"}:::decision
  Route -->|"❓ 模糊 / 多解读"| RM["📝 /ai-requirement<br/>澄清 · 批量追问"]:::step
  Route -->|"✅ 清楚"| Design
  RM --> Gate{"🚦 Requirement Gate"}:::decision
  Gate -->|"⛔ BLOCKED"| RM
  Gate -->|"🟢 READY · WHAT 已冻"| Design["🎨 /ai-design · DiagramMind<br/>分析取证 → 出系统图"]:::step
  Design --> Render{"🖼️ 渲染成功?"}:::decision
  Render -->|"❌ 否"| Design
  Render -->|"✅ 是"| Code["🔧 /ai-code<br/>最小 diff + 自检"]:::step
  Code --> Self{"🧪 自检绿?"}:::decision
  Self -->|"❌ 否"| Code
  Self -->|"✅ 是"| Drift{"🧭 drift 检测<br/>图是否还符合代码"}:::decision
  Drift -->|"⚠️ 有漂移"| Design
  Drift -->|"✅ 无漂移"| Notify(["📦 交付 + 记忆落盘"]):::done

  classDef actor fill:#fde8e8,stroke:#e07272,color:#7a1f1f,stroke-width:1.5px
  classDef decision fill:#fdf2e0,stroke:#dda94f,color:#5c3c07,stroke-width:1.5px
  classDef step fill:#e8f0fe,stroke:#5b8fd6,color:#173a6b,stroke-width:1.5px
  classDef done fill:#e6f6ec,stroke:#5aa877,color:#14452a,stroke-width:1.5px
```

## 说明

- **两条入口**：模糊需求先走澄清，清楚的需求直接进设计 —— 这是 R1（未过 Gate 不开发）的业务表达。
- **三个回流环**：Gate BLOCKED 回澄清、渲染失败回设计、drift 有漂移回设计。回流是常态不是异常。
- **终止条件**：自检绿 + 无漂移，二者缺一不可。
- micro-fix（typo / 唯一解读）可跳过澄清与设计，但必须有一行可证伪的判据。

## 未知项

| # | 问题 | 状态 | 需要 |
|---|------|------|------|
| 1 | 自检"绿"的判定口径 | 已确认 | 见 `shared/verification-policy.yaml` |
| 2 | drift 检测是否进 CI | 未知 | 查 `.github/workflows` |

## 证据

| 节点/边 | 来源 |
|---------|------|
| Gate READY 才开发 | `shared/core.md:14` |
| 回流环 | `shared/core.md:35-40` |
| 验证档位 | `shared/verification-policy.yaml` |
| drift 检测 | `scripts/verify_skill_drift.py` |
