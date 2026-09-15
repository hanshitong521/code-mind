# Benchmark 方法论

> 目标不是「证明省了 Token」，而是**证明在任务成功率与证据完整性不下降的前提下，成本真的降了**。
> 上位规则：`references/spec-v2.md` §7 / §13；`references/spec-v1.md` §24 / §25。

---

## 1. 为什么不能只放容易压缩的 Build Log

Build Log 高度模板化，任何压缩器都能拿到 80% 的数字。若基准集只有它，会得到**虚高的节约率**，
而真实瓶颈（代码搜索、DB 排查、跨模块接缝、日志定位）一个都没覆盖，上线即翻车。

**强制覆盖的 8 类 kind**（见 `benchmarks/tasks.yaml`，每类 ≥2 条）：

| kind | 考什么 | 典型反例 |
|---|---|---|
| `small-change` | 是否**不加载**多余上下文 | 为改 1 行读 5 个文件 |
| `feature` | 增量读取 + 复用检索 | 全量重写而非 grep 复用 |
| `debug` | 证伪能力与证据链 | 直接改码「试试」 |
| `database` | 结构与数据的真实交互 | 凭记忆写表名 |
| `cross-module` | 接缝契约一致性 | 只改一端就宣称完成 |
| `test-fix` | 是否用删断言蒙混 | 放宽断言让测试变绿 |
| `log-heavy` | 结构化筛选而非整读 | 整段日志进上下文 |
| `cross-domain` | 多域结论不自相矛盾 | 各域各说各话 |

Build Log 类任务**可以放进基准集**，但不得单独构成基准集。

---

## 2. 同任务 A/B 的固定项（缺一项则结果作废）

| 固定项 | 要求 | 记录位置 |
|---|---|---|
| `repo_commit` | 两侧同一 commit SHA（`git rev-parse HEAD`） | 报告头部 |
| `model_version` | 同一模型与同一版本号 | 报告头部 |
| `task_input` | 逐字相同的任务原文（从 `tasks.yaml` 取，禁改写） | 报告附录 |
| `acceptance` | 同一验收判据（从 `tasks.yaml` 取） | 报告附录 |
| `environment` | 同一 OS / Python / 依赖 / DB 快照 / 夹具主键 | 报告头部 |

A = 基线（未启用 SkillMind）；B = 启用 SkillMind。**两侧除被测变量外不得有任何差异**。
若某固定项客观上无法固定（如线上日志时间窗不可重现），必须显式记录并在结论中降级置信度。

---

## 3. 随机性处理

- 同一任务**至少重复 3 次**（`tasks.yaml: protocol.repeat`），报**中位数**，同时报 min/max 离散度。
- 记录随机性来源：模型采样温度、工具返回顺序、网络抖动、DB 缓存命中。
- 方差大的任务（max/min > 2.0）**不得**只报中位数，必须报区间并标注不稳定。
- 单次结果只能用于排查异常，不能作为结论。

---

## 4. Phase 0 的取舍：15–30 条高质量 > 50 条低质

- 先做 **15–30 条**有代表性的真实任务（本仓当前 18 条），逐条可追溯来源。
- 判定「高质量」的三条：① 来自真实工单/真实缺陷；② 有明确、可机械判定的 acceptance；
  ③ 覆盖的 kind 与 level 不与其他条目重复。
- 低质量任务的典型特征：acceptance 写成「改好即可」、无风险等级、baseline 是估计值。
- 扩展顺序：先补短板 kind，再补高 level，最后才增加同质条目。

---

## 5. Successful Task Cost（综合指标）

单看 Token 会被「用更多次调用换更少 Token」作弊。用综合成本：

```
SuccessfulTaskCost = w1·norm(InputTokens)
                   + w2·norm(OutputTokens)
                   + w3·norm(ToolCalls)
                   + w4·norm(Latency)
                   + w5·norm(Rework)
                   + w6·norm(ErrorCost)
```

规则：

1. **先正规化再相加**——各项量纲不同（tokens 万级、latency 秒级、rework 次数级），
   必须先把 A/B 两侧按同一基准正规化（`norm(x) = x / max(A,B)`）才能相加。
2. **只在 Successful Task 上算**——失败任务的低成本没有意义，失败单独进失败率统计。
3. `ErrorCost` = 失败调用产生的成本 + 因错误导致的返工成本，禁止记 0 掩盖。
4. 权重默认：Token 0.35 / ToolCalls 0.20 / Latency 0.15 / Rework 0.20 / ErrorCost 0.10；
   改权重必须同 PR 说明理由并重跑全部条目。
5. **禁止**只报压缩率；必须与 `TaskSuccess`、`EvidenceRetention` 同时呈现（spec-v2 §7）。

---

## 6. 报告必须同时给出的原始指标

`TaskSuccess · InputTokens · OutputTokens · ToolCalls · DuplicateCalls · Latency · Rework · EvidenceRetention`

- `EvidenceRetention`：P0 证据（报错原文、失败断言、关键行号、SQL 状态）保留率，**任一丢失即 FAIL**，
  与成本数字无关。
- `DuplicateCalls`：同一工具同参数重复调用次数，是「不重复调用」优先级的直接度量。
- 分数与原始指标**必须同屏出现**；用分数掩盖原始指标 = 反模式（spec-v2 §15）。

---

## 7. 结论判定

| 判定 | 条件 |
|---|---|
| PASS | 成本下降且 `TaskSuccess` 不降、`EvidenceRetention` = 1.0、无权限扩大 |
| FAIL | 丢 P0 证据 / 成功率降 / 权限扩大 / 该用找不到（Recall 崩）任一命中 |
| 待定 | 成本下降但样本 < 3 次重复，或离散度过大未解释 |

FAIL 与「待定」都不得进入默认路径；须回退到 `docs/MIGRATION.md` 的回滚步骤。

---

## 8. 相关文件

| 文件 | 内容 |
|---|---|
| `benchmarks/tasks.yaml` | 18 条基准任务与 baseline |
| `benchmarks/runner.md` | 执行方式、对比维度、报告位置、环境隔离 |
| `docs/ACCEPTANCE.md` | 可勾选验收表与验证命令 |
| `references/spec-summary.md` | 常驻摘要 |
