---
name: ai-design
description: Design before code. Use when scoping a change, choosing approaches, writing Handoff, or user says /ai-design. Load references/refs.md for gates; do not implement production code here.
---

# ai-design

**WHAT 未冻结 → 先 RequirementMind。HOW（模块/接缝/验证档）才用本 skill。**

## G0（必答）

1. 改什么 / 不改什么 / 完成判据（1 命令可证伪）？
2. 若 ≥2 解读未选 → 停，问用户或回 RM。
3. 产出：plan 或 Handoff（见 `references/handoff-template.md`），**禁止**直接 `/ai-code` 开写。

## 细则

单读 `references/refs.md`（禁批读）。命中 gate-router 信号再读对应节。

## 负代码四问（新建文件/依赖/抽象前）

同职责已存在？为何不能改现有？增概念还是减？可删？全过才建，否则写进「明确不做」。
