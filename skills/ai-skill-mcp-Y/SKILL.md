---
name: ai-skill-mcp-Y
description: Audit/rewrite Skills, MCP exposure, AGENTS.md. Use when 优化skill、MCP误触发、AGENTS瘦身、skill大扫除、governance. Not for product coding, Java/SQL, 查日志, /ai-code.
---
trig:优化skill|审计MCP|AGENTS瘦身|误触发|governance prio:本页>项目rules
load:本页; ref命中单读; 禁批读; 禁默认读 spec-v1
axiom:最小充分上下文; 正确>证据>安全>token; 不加载>不重复>再压缩

# ai-skill-mcp-Y

干什么: 审计 Skill/MCP/AGENTS → 分类 → 按配方改 → 4类 trigger 自检。
默认最小: 先报告后改。用户说「直接改」才动文件。
何时升级: 跨仓复用同一缺陷 ≥3 次才升 STOP; 规范争议才读 spec-v1。

G0: 范围=skill|mcp|agents|all(默认all,只扫实际存在的)
G1: inventory — `python scripts/inventory.py --root <项目根>` 或读 references/inventory.md
G2: 每条资源跑 4类 trigger — references/trigger-tests.md
G3: 分类 KEEP|OPTIMIZE|MERGE|SPLIT|LAZY-LOAD|DISABLE-CANDIDATE|BLOCK
G4: 填 templates/audit-report.md; 未授权改则停
G5: 改 — 一次一资源, 配方 references/apply.md
G6: 改后复跑 trigger; Hard Gate FAIL 则回滚该资源

Hard Gate(任一即 FAIL): 丢P0证据|成功率降|权限扩大|该用找不到(Recall崩)
禁: 自动删灾备/事故/迁移 skill; 只报压缩率; 多层都做 Router

ref:inventory→references/inventory.md | trigger→references/trigger-tests.md | 改→references/apply.md | 报告→templates/audit-report.md | 摘要→references/spec-summary.md | 全文V1仅点名→references/spec-v1.md
STOP:写业务码|micro-fix|/ai-code|查日志|对账|整读V1当开工
