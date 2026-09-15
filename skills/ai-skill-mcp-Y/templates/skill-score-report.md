# Skill Score Report

Date:  Skill:  Version:  改前版本:  Owner:
Root:  Commit:  模型/版本:  A/B 重复次数:

Verdict: PASS | OPTIMIZE | BLOCK

## 1 Hard Gate（任一 FAIL → Verdict 直接 BLOCK，禁被其他维度高分抵消）

| Gate | 判据 | 结论 | 证据一句 |
|---|---|---|---|
| 正确 Gate | `TaskSuccess` 不下降；DoD 逐条有 `cmd+exit`/SELECT | | |
| Evidence Gate | `EvidenceRetention = 1.0`（P0 证据零丢失） | | |
| 安全 Gate | 权限未扩大；destructive 仍 `execute` + 二次确认；供应链非 BLOCK | | |
| 冲突控制 | 无新增严重重叠（`registry.json.overlap.severity`） | | |
| Trigger 四类 | P / N / B / C 全过，Recall 未崩 | | |
| 回滚 | 回滚点明确（改前路径 / git ref） | | |
| 真实 A/B | ≥3 真实任务，含 ≥1 复杂 Debug、≥1 跨模块 | | |

## 2 原始指标（必填；禁只给分数）

| 指标 | A 治理前 | B 治理后 | Δ | 单位 | 来源 |
|---|---|---|---|---|---|
| TaskSuccess | | | | 0–1 | 验收逐条 |
| InputTokens | | | | tokens | telemetry.context_tokens_loaded |
| OutputTokens | | | | tokens | telemetry.result_tokens |
| ToolCalls | | | | 次 | telemetry.call_count |
| DuplicateCalls | | | | 次 | telemetry 去重计数 |
| Latency | | | | ms | telemetry.latency_ms |
| Rework | | | | 次 | telemetry.rework |
| EvidenceRetention | | | | 0–1 | P0 清单逐条核对 |

综合：Successful Task Cost = Tokens + ToolCalls + Latency + Rework + ErrorCost（各维归一化后相加）

无效上下文下降: %（目标 ≥50%；八级优先序见 references/token-loading.md）

## 3 评分（公式 references/spec-v2.md §3.3）

| 分项 | 权重 | 原始值 | 归一化 0–100 |
|---|---:|---|---|
| 成功率 | 40% | | |
| 准确率 | 30% | | |
| Token 效率 | 15% | | |
| 速度 | 10% | | |
| 稳定性 | 5% | | |
| **总分** | 100% | | |

Grade: 生产级(95–100) | 强(90–94) | 可用待优化(80–89) | 上线前复查(70–79) | 重设计/禁用(<70)
baseline_defaulted: true | false

原始记录（与分数同时展示）:

```json
{"skill_id":"","metrics":{"success_rate":0,"accuracy":0,"token_avg":0,"time_avg":0,"stability":0,"bug_escape":0},
 "baseline":{"token_avg":0,"time_avg":0}}
```

## 4 Trigger 四类结论

| 类 | 用例数 | 通过 | 失败句（原文） | 处置 |
|---|---:|---:|---|---|
| Positive 必触发 | | | | |
| Negative 禁触发 | | | | |
| Boundary 模糊 | | | | |
| Conflict 争用 | | | | |

Trigger Precision = /  Trigger Recall = / Misfire Rate =
Strong-model 检查（是否 18 步食谱 / 全仓必读 / 泛 MUST）:

## 5 Evidence 保留结论

| P0 证据 | 应有 | 压缩后仍在 | 位置 |
|---|---|---|---|
| AssertionError / Exception 类型 | | | |
| failing file / line | | | |
| SQLState / DB error code | | | |
| requestId / traceId | | | |
| 安全权限判定结果 | | | |
| acceptance criteria 逐条结论 | | | |
| 关键返回码 | | | |

EvidenceRetention = 保留 / 应有 =
已压缩（可压缩类）: 重复成功日志 · 无变化记录 · 重复 stack trace · 无关 metadata · 可由引用重取的大文本
禁: 只报压缩率；删 P0 证据换指标。

## 6 四类测试结论

| 类 | 结论 | 证据 |
|---|---|---|
| 功能 | | |
| 回归 | | |
| 对抗 | | |
| Benchmark | | |

## 7 A/B 固定项核对

| 固定项 | 值 | 一致 |
|---|---|---|
| repo commit | | |
| model / version | | |
| task input | | |
| acceptance criteria | | |
| 环境 | | |

任务覆盖（七类）: 小修改 [ ] 普通 Feature [ ] Debug [ ] 数据库 [ ] 跨模块 [ ] 测试修复 [ ] 高风险/大日志 [ ]

## 8 Verdict 理由

PASS | OPTIMIZE | BLOCK 一句:
未覆盖项 / 已知残留风险:

## 9 Rollback

回滚点: 改前路径 / git ref
回滚动作: 一步可执行
回滚后验证:

## 10 Next 3

1.
2.
3.

禁: 只报压缩率 | 分数掩盖原始指标 | EvidenceRetention 抽检 | A/B 不固定 | 无回滚点 | Hard Gate FAIL 仍 PASS
