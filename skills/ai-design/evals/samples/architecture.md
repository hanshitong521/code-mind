# 架构图

> 分层看 code-mind：谁依赖谁，契约在哪一层。

![架构图](assets/architecture.svg)

```mermaid
architecture-beta
    group client(cloud)[客户端]
    service user(internet)[用户 / Agent] in client

    group entry(cloud)[技能入口层]
    service req(server)[RequirementMind] in entry
    service des(server)[DiagramMind] in entry
    service code(server)[ai-code] in entry
    service con(server)[concise-mind] in entry

    group contract(cloud)[契约层]
    service core(database)[core.md] in contract
    service hs(database)[handoff-schema] in contract

    group pack(cloud)[领域包]
    service j8(server)[java8] in pack
    service ads(server)[ads] in pack

    group tool(cloud)[工具层]
    service vh(server)[validate_handoff] in tool
    service dr(server)[drift] in tool

    user:R -- L:req
    req:R -- L:des
    des:R -- L:code
    code:R -- L:con
    req:B -- T:core
    des:B -- T:hs
    code:B -- T:vh
    vh:R -- L:dr
    j8:L -- R:code
    ads:L -- R:code
```

## 说明

- **契约层被所有技能层依赖，反向无依赖** —— 这是"下层禁改上层真源"的物理体现。
- **工具层不参与推理**：只做校验与构建，是 fail-closed 的闸门（`validate_handoff` FAIL → 禁交 `/ai-code`）。
- **领域包是叶子依赖**：只被技能层读取，自身不依赖任何技能。
- `docs/diagram/` 是 DiagramMind（设计层）的产物，供人和下游 Agent 快速理解系统。

## 未知项

| # | 问题 | 状态 | 需要 |
|---|------|------|------|
| 1 | `capability-registry.yaml` 是否被运行期读取 | 待确认 | 查是否有脚本引用 |
| 2 | `.contextmind/task.active.json` 的写入方 | 未知 | 查 handoff_to_task_bundle |

## 证据

| 节点/边 | 来源 |
|---------|------|
| 五层职责 | `shared/core.md:12-19` |
| 契约文件 | `shared/*.yaml` |
| 工具脚本 | `scripts/*.py` |
| 领域包 | `domain-packs/java8`, `domain-packs/ads` |
