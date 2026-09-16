# 工作流与上下游

> 根文档 `SKILL.md` 的 `ref:` 路由表命中「12 步工作流」或「上下游链路」时读本页。

## 1 12 步工作流（规范 §25）

```
1  Resolve target        → gitctx.resolve_context
2  Load requirement      → --requirement <file>（已过 secret 过滤）
3  Collect diff          → changed files + hunks
4  Deterministic layer   → native-java/native-vue + javac/PMD/CPD/SpotBugs/Semgrep/Knip
5  Minimal context       → packer.build_context_pack（按风险扩张，默认只审 diff）
6  Semantic reviewer     → riskrouter 决定 1~2 个 reviewer + persona
7  Normalize findings    → 稳定 id、分类、修复路由
8  Validate high risk    → evidencevalidator（RV-001..003、动态入口、severity 打假）
9  Dedup + baseline      → 同问题多来源合并；历史债 vs 新增债
10 Score + Gate          → 10 维评分 + 硬门槛 + PASS/WARN/BLOCK/UNKNOWN
11 Repair routing        → SAFE_AUTO_FIX / WRITER_FIX / MANUAL_DECISION
12 Re-run gate           → codehealth verify（修复后必须重新证明）
```

## 2 与上下游

```
ai-requirement → Writer → CodeHealthMind PRE-GATE → TestMind → CodeHealthMind POST-GATE → Merge
```

- **PRE-GATE**：结构 · 复杂度 · 死代码 · 重复 · 明显 bug · 过度设计。
- **POST-GATE**：测试证据 · 回归 · 修复引入的新债 · 最终 delta。
