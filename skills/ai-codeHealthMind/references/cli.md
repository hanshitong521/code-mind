# CLI 参考（命令 · 目标 · 输出 · 失败排查）

> 根文档 `SKILL.md` 的 `ref:` 路由表命中「命令 / 目标选择 / 输出格式 / 退出码 / 失败排查」时读本页。
> 入口恒为 `python codehealth.py <command> [flags]`（零依赖，无需 PYTHONPATH；Python ≥3.10）。

## 1 命令

| 命令 | 用途 |
|---|---|
| `review` | 跑 Gate，出报告 |
| `fix` | 出修复计划；`--apply` 才动代码（只动可证安全的） |
| `verify` | 修复后重跑 Gate 并与上一轮对比（规范 §34 强制） |
| `explain CHM-000123` | 解释单条 finding 的完整证据链 |
| `baseline --show\|--update` | 查看/刷新基线（历史债不阻断，新增债才阻断） |
| `probe` | 真实探测工具链可用性与版本 |
| `init` | 写 `.codehealth.yml` |

## 2 目标选择（6 选 1，默认 diff）

```
--diff | --staged | --commit <sha> | --range <a>..<b> | --file <path> | --repo
```

## 3 输出

```
--format console|json|markdown|sarif   -o <file>
```

退出码固定：`0` PASS/WARN · `1` BLOCK · `2` 工具或配置错误 · `3` UNKNOWN

## 4 失败时怎么读

1. `codehealth probe` → 哪些工具真的可用、什么版本
2. 报告里的 `tools[]` → 每个 provider 的真实命令、耗时、状态
3. `tool_errors[]` → `kind` 是 `MISSING` / `TIMEOUT` / `NONZERO_EXIT` / `MALFORMED_OUTPUT` / `PARTIAL_OUTPUT`
4. `evidence_gap=true` → 有结论因缺证据而无法成立；此时 Gate 只能是 WARN/UNKNOWN，不会是 PASS
