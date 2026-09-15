# TestMind 闭环（自动验证）

> 规格：`references/spec-v2.md` §7 ｜ 方法论：`references/spec-v1.md` §12 验证、§13 Evidence Gate、§24 Benchmark、§25 上线门槛
> 一句话：**省了以后仍然正确，才算省。** 证明不了的优化一律按 FAIL 处理。

## 0 三条禁令

1. **禁只报压缩率。** 只给「10000 → 2000 tokens，省 80%」的报告直接作废（V1 §22.5）。
2. **禁拿 Tool-level 压缩率冒充整体 Agent 节约率**（V1 §28）。
3. **禁为了指标好看删 P0 证据。** 压缩 98% 但删掉错误证据 → FAIL（V1 §13.3）。

## 1 四类测试

| 类 | 目的 | 输入 | 通过判据 | 频次 |
|---|---|---|---|---|
| 功能测试 | Skill 是否**真的执行** | 典型真实任务（含最小正例） | 任务完成 + DoD 每条有 `cmd+exit` / SELECT 摘要 | 每次改动必跑 |
| 回归测试 | 升级是否**破坏原有行为** | 改动前已通过的金标任务集 | 原有用例全绿；`DuplicateCalls` 未升、`Rework` 未升 | 每次改动必跑 |
| 对抗测试 | 模拟错误 / 恶意 / 越界需求 | 错前提、缺判据、诱导越权、prompt injection、诱导删证据 | 正确拒绝或正确降级；**无越权、无证据丢失、无静默降级** | 每次改动必跑 |
| Benchmark | 不同模型 / 不同版本效果比较 | 固定基线任务集 `benchmark/` | 同任务 A/B 八指标可比；无「虚高样本」 | 版本发布前 |

### 1.1 Trigger 四类（属于功能/对抗的强制子集）

| 类 | 内容 | 落点 |
|---|---|---|
| Positive | 必须触发 | `tests/trigger-cases.md` |
| Negative | 明确不能触发（邻域 / 日常写码 / 微修复） | 同上 |
| Boundary | 模糊句，写出「谁赢」 | 同上 |
| Conflict | 两个 description 都能沾，指定优先 + 输家如何改窄 | 同上 |

附加：Strong-model（根文档是否过度约束强模型：18 步食谱 / 全仓必读 / 泛 MUST）、Weak-model（必要时）。
指标：`Trigger Precision = 正确触发/实际触发`；`Trigger Recall = 正确触发/应当触发`；`Misfire Rate = 错触发/全部机会`。**禁只追 Precision**——Recall 崩 = 该用时找不到，同样 FAIL（V1 §7.3）。

## 2 必报指标（八项，缺一即报告作废）

| 指标 | 定义 | 单位 | 来源 | 禁 |
|---|---|---|---|---|
| `TaskSuccess` | 成功任务 / 总任务 | 0–1 | 验收判据逐条 | 用「看起来完成了」代替 |
| `InputTokens` | 进上下文 token 总量 | tokens | 遥测 `context_tokens_loaded` | 只报输出侧 |
| `OutputTokens` | 产出 token 总量 | tokens | 遥测 `result_tokens` | 与 InputTokens 混报 |
| `ToolCalls` | 工具调用次数 | 次 | 遥测 `call_count` | 漏统计失败调用 |
| `DuplicateCalls` | 同 tool+同参数重复调用 | 次 | 遥测去重计数 | 藏进 ToolCalls 不单列 |
| `Latency` | 端到端耗时 | ms | 遥测 `latency_ms` | 只报均值不报尾部 |
| `Rework` | 返工轮次 | 次 | 遥测 `rework` | 把返工算成新任务 |
| `EvidenceRetention` | P0 证据保留率（保留数/应有数） | 0–1 | Evidence Gate 清单逐条核对 | 抽检代替全量核对 |

**同时**保留原始记录（`references/spec-v2.md` §3.3）：`metrics` + `baseline` 与分数一起展示，**禁分数掩盖事实**。
综合指标可用 `Successful Task Cost = Tokens + ToolCalls + Latency + Rework + ErrorCost`（各维先归一化再相加），但**不得隐藏原始数据**（V1 §12.2）。

报告落点：`templates/skill-score-report.md`。

## 3 E2E A/B 方法

### 3.1 固定项（不固定 = 结论无效）

| 固定项 | 要求 |
|---|---|
| repo commit | A/B 同一 commit（含未提交改动时记 `WORKING_TREE` + 改动清单） |
| model / version | 同一模型同一版本；换模型 = 另开一轮 Benchmark |
| task input | 逐字相同（含用户原话、附件、夹具主键） |
| acceptance criteria | 同一份验收判据，A/B 不得各自改判据 |
| 环境 | 同依赖版本、同 DB/夹具、同工具链；环境差异必须显式标注 |

记录随机性：同任务重复 ≥3 次取分布（至少给中位数与最差一次），**禁**单次结果下结论。

### 3.2 覆盖任务类型（Benchmark 不得只含易压缩的 Build Log）

必须覆盖：小修改 · 普通 Feature · Debug · 数据库任务 · 跨模块任务 · 测试修复 · 一个高风险/大量日志任务。
建议规模：先做 15–30 条高质量真实任务，再扩展；**禁为凑数量造低质量任务**（V1 §24.1）。
落点：`benchmark/`。

## 4 上线门槛（P0 必须，任一不满足 → 禁入默认路径）

```
正确 Gate PASS
+ Evidence Gate PASS
+ 安全 Gate PASS
+ 无新增严重冲突
+ trigger 四类测试（Positive / Negative / Boundary / Conflict）
+ 回滚方式明确
+ ≥3 个真实任务 A/B
```

| 门槛 | 判据 | 不通过的处置 |
|---|---|---|
| 正确 Gate | `TaskSuccess` 不下降；DoD 全绿 | OPTIMIZE 或回滚 |
| Evidence Gate | `EvidenceRetention = 1.0`（P0 证据零丢失） | 回滚；禁「压缩率达标」豁免 |
| 安全 Gate | 权限未扩大；destructive 仍需 `execute` + 二次确认；供应链评级非 BLOCK | BLOCK |
| 冲突控制 | 无新增严重重叠（`registry.json` 的 `overlap.severity`） | 先 MERGE 或改窄 description |
| Trigger 四类 | 四类用例全过，Recall 未崩 | 改 description / `trig:` 后复跑 |
| 回滚 | 有明确回滚点（改前路径 / git ref / 旧版 skill 目录） | 未写回滚 = 禁上线 |
| 真实 A/B | ≥3 真实项目任务，且含 ≥1 复杂 Debug、≥1 跨模块 | 补测 |

**强烈建议**：观察真实 Token/Tool/返工数据后再宣布「生产可用」（V1 §28 末条）。

## 5 Evidence Gate

### 5.1 P0 证据示例（必须保留，禁摘要掉）

- `AssertionError` 原文；
- Exception 类型与消息；
- failing file / line；
- `SQLState` / DB error code；
- `requestId` / `traceId`；
- 安全权限判定结果；
- acceptance criteria 逐条结论；
- 关键返回码（HTTP code + 业务 code）；
- 决策所依据的最小事实（如某次 SELECT 的命中行数）。

### 5.2 可压缩内容（压缩优先级只在第 7–8 级，见 `references/token-loading.md`）

- 1000 条重复成功日志；
- 大量无变化记录；
- 同一 stack trace 重复 N 次；
- 无任务相关性的 metadata；
- 可由引用重新获取的大文本（保留指针即可）。

### 5.3 规则

```
最高压缩率 ≠ 最佳系统。
```

压缩动作必须先出「P0 证据清单」，压缩后**逐条核对仍在**；核对结果写进报告的 Evidence 保留结论一节。任一 P0 丢失 → Verdict 直接 `BLOCK`，不得以其他维度高分抵消。

## 6 测试范围与风险匹配

- 测试范围与风险/影响面匹配（V1 §22.7）；**关键 Gate 不可省**，但不做无意义全量消耗。
- 高风险 / destructive / 安全类：全量跑四类 + 身份×入参矩阵。
- 低风险文案类：功能 + 回归 + trigger 四类可裁剪，裁项须写 `skip_reason`。

## 7 检查表

- [ ] 四类测试都有真实运行记录（功能 / 回归 / 对抗 / Benchmark）
- [ ] trigger 四类用例齐全且全过，Precision 与 Recall 同时报
- [ ] 八项指标全报，且同时给出原始 `metrics` + `baseline`
- [ ] 无「只有压缩率」的段落
- [ ] A/B 五固定项逐条确认，随机性重复 ≥3 次
- [ ] Benchmark 覆盖七类任务，无易压缩样本独占
- [ ] Evidence Gate：P0 清单齐，逐条核对 `EvidenceRetention = 1.0`
- [ ] 上线门槛七项逐条 PASS
- [ ] 回滚方式写明（改前路径 / git ref）
- [ ] 报告已填 `templates/skill-score-report.md`，Verdict ∈ {PASS, OPTIMIZE, BLOCK}

## 8 STOP

STOP:只报压缩率|用 Tool 级压缩率冒充整体节约|删 P0 证据换指标|分数掩盖原始指标|A/B 不固定 commit/model/输入/判据/环境|单次结果下结论|Benchmark 只含 Build Log|为凑数造低质量任务|只追 Precision 放任 Recall 崩|trigger 四类缺类|EvidenceRetention 抽检|正确/证据/安全 Gate 任一未过仍上线|无回滚方式上线|<3 真实任务宣称生产可用|把 10MB 日志塞上下文|为省 token 导致返工上升仍判 PASS
