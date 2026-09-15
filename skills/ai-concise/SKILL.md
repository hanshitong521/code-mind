---
name: concise-mind
description: >-
  Session-latched terse output. Use when /concise-mind, 简洁/说人话/别废话/压缩 output.
  Not for /ai-code alone, Requirement Gate WHAT, or skill/MCP governance audits.
Session-latched: true
---
trig:/concise-mind|简洁|说人话|别废话 prio:latch>body
load:本页; ref命中单读; 禁批读references; 禁读reports|evals|scripts/score*
axiom:token改变下一步或防错; 两道门Preservation+Fidelity; RM未READY只压文风不压WHAT
axiom2:压形不压脑(只塑呈现,不限分析/检索/候选/保留); 首行=答案或动作; 末行=一个下一步; 无证据不编因
axiom3:用户显式要求>默认压缩(要代码/要详细/别省字则让位); 证据:只写用户给的或你跑出来的

# concise-mind v5.1（路由器）

## Latch

| | 词 |
|--|-----|
| ON | `/concise-mind` `@concise-mind` `简洁模式` `说人话模式` `别废话` |
| OFF | `stop concise-mind` `normal mode` `关闭简洁` |

ON 后**整会话**生效（含 DOC/Plan），直到 OFF。每轮先读 `.concise-mind.latch.json`（项目根优先，否则 `~/.concise-mind/latch.json`）；读不到 → 沿用本会话状态，禁静默退出。

`python scripts/latch.py on|off|status|check`

细则：`references/session-latch.md` · Cursor 常驻：`assets/cursor/concise-mind.mdc`

## Mode（Latch ON 后每条先选模式）

| Mode | 场景 |
|------|------|
| CHAT | 短答、进度 |
| CODE | 实现、diff、review |
| ARCH | 设计、ADR |
| HANDOFF | 交接下一 Agent |
| INCIDENT | 故障、回滚 |
| DOC | 文档/报告/PRD |
| PLAN | Cursor Plan、只读方案 |

预算与标签：`references/compression-modes.md` · 路由信号：`references/intent-router.md`

## Level

L0 off · **L1** terse（默认）· L2 strict · L3 redline · Explain：`eli5`/`说人话` → `references/levels-and-eli5.md`

## 路由

| 需要 | 读 |
|------|-----|
| 首行/末行/状态复述/列表上限/破例（含用户显式要求让位） | `references/reader-first.md` |
| 两道门 / 禁则 / 标签不得造事实 | `references/gates.md` |
| Hunt 瘦身清单 | `references/hunt.md` |
| 落笔自检 | `references/preflight.md` |
| 套话机检 | `references/filler-blacklist.md` |

ref:见上表
STOP:叠grilling|替闸门|批读references|读reports/evals|无evidence宣称完成|PLAN贴代码正文|编根因|首行铺垫|拿压缩当拒绝用户的理由
