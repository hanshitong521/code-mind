# SkillMind 评分引擎 — 可复现、可审计、不掩盖事实

> 规格：`spec-v2.md` §3.3 / §7 / §14.1 / §14.4 ｜ 实现：`scripts/score.py`

## 0. 铁律

1. **原始指标与分数必须同时输出**，禁止只存分数（§3.3 / §15）。任何报告里出现「分数」而看不到 `metrics` 的，一律判 FAIL。
2. **可复现**：同输入必得同输出。不引入时间、随机、环境相关的项；`recorded_at` 只是元数据，不参与计算。
3. **权重不可私改**：改权重 = 改 spec。权重是常量，写在 `score.py::WEIGHTS`，任何调用方都无法覆盖。

## 1. 公式（§3.3）

```
Score = 成功率×40% + 准确率×30% + Token效率×15% + 速度×10% + 稳定性×5%
```

| 分项 | 权重 | 定义 | 归一化 |
|---|---|---|---|
| `success_rate` | 0.40 | 任务成功 / 总调用 | `clamp01(x) × 100` |
| `accuracy` | 0.30 | 无返工 / 无 bug escape | `clamp01(x) × 100` |
| `token_efficiency` | 0.15 | `baseline.token_avg / token_avg` | `clamp01(·) × 100`，上限 100 |
| `speed` | 0.10 | `baseline.time_avg / time_avg` | `clamp01(·) × 100`，上限 100 |
| `stability` | 0.05 | 方差小 / 无 crash | `clamp01(x) × 100` |

`clamp01(x) = 0 if x<0 else (1 if x>1 else x)`，来自 `_common.clamp01`（禁自行实现）。

- 三项比例类输入按 0–1 语义，超界被夹到 `[0,1]`，不允许出现负分或 >100 的分项。
- 两项均值类**越大越好必须换算成比值**：token/耗时优于基线 → 比值 >1 → 夹到 1.0 满分；劣于基线 → 比值 <1 → 按比例扣分。**禁止直接拿 token 数当分**。
- 缺项处理：比例类缺省记 0，均值类缺省记 1.0 倍基线（即不奖不罚），并在 `warnings` 里逐条说明。**缺项必须留痕，禁静默**。
- `score` 保留两位小数（`_common.round2`）。

### 与 §14.4 示例的一处出入

§14.4 的示例输入（0.95 / 0.93 / token 2500 / time 15 / 0.98，基线 3000 / 20）手算：

```
subscores = 95.0 / 93.0 / 100.0 / 100.0 / 98.0
score = 95×0.40 + 93×0.30 + 100×0.15 + 100×0.10 + 98×0.05
      = 38 + 27.9 + 15 + 10 + 4.9 = 95.8
```

§14.4 示例里写的是 `96.2`，与 §3.3 公式相差 0.4。**以 §3.3 公式为准**（本实现输出 95.8）。两份 spec 冲突时公式优先于示例值。

## 2. 基线

未提供 baseline 时用默认值并在输出里标注：

```json
{"baseline": {"token_avg": 3000.0, "time_avg": 20.0}, "baseline_defaulted": true}
```

- 也可把 baseline 嵌在 metrics 里：`--metrics-json '{"...":0, "baseline":{"token_avg":3000}}'`。
- baseline 字段非法（缺失、≤0、非数值）→ 回落默认值 + warning，**不静默**。
- 基线的作用是**同口径对比**：换了基线就必须重算，`record` 会把当时的基线一起存下来，事后可复算。

## 3. 分档（§3.3）

| 分数 | grade | 中文档位 | 处置 |
|---|---|---|---|
| 95–100 | `Production Grade` | 生产级 | 可上关键路径 |
| 90–94 | `Strong` | 强 | 可用 |
| 80–89 | `Usable` | 可用待优化 | 记优化项 |
| 70–79 | `Review Before Release` | 上线前复查 | 上线前必须复检 |
| <70 | `Redesign or Disable` | 重设计或禁用 | 重设计；**不是自动删除**（§3.4 只降级不删） |

分档是**动作指令**，不是标签。`<70` 产出的是 `DISABLE-CANDIDATE` 候选，**禁止自动删除 Skill、自动改权限、自动改生产 Tool**。

## 4. 记录格式（§14.4）

`record` 落盘一条完整记录（契约 `schemas/score-record.schema.json`）：

```json
{
  "schema_name": "skillmind-score-record", "schema_version": 1,
  "skill_id": "ai-code", "recorded_at": "2026-09-15T13:05:16Z",
  "metrics": {"success_rate": 0.95, "accuracy": 0.93, "token_avg": 2500,
              "time_avg": 15, "stability": 0.98},
  "baseline": {"token_avg": 3000.0, "time_avg": 20.0},
  "baseline_defaulted": true,
  "subscores": {"success_rate": 95.0, "accuracy": 93.0, "token_efficiency": 100.0,
                "speed": 100.0, "stability": 98.0},
  "weights": {"success_rate": 0.40, "accuracy": 0.30, "token_efficiency": 0.15,
              "speed": 0.10, "stability": 0.05},
  "score": 95.8, "grade": "Production Grade",
  "warnings": ["未提供 baseline，使用默认基线 token_avg=3000.0 time_avg=20.0（§14.4）"]
}
```

- `metrics` **原样保留全部原始指标**，包括未参与打分的 `bug_escape` / `tool_calls` / `latency_ms` / `rework` / `evidence_retention` 等。压缩或丢弃原始值即违规。
- 存储：`<root>/.skillmind/scores.json`，外层 `{"schema_name":"skillmind-scores","records":[…]}`，**追加**不覆盖。
- `record` **不写回** `registry.json`（那是 `registry_build.py` 的产物）。Router 在读不到 `registry.score` 时会从 `scores.json` 取最新分补位，保持单向只读。

## 5. 命令

```bash
# 记录一次评分（人类可读）
python3 scripts/score.py record --skill-id ai-code \
  --metrics-json '{"success_rate":0.95,"accuracy":0.93,"token_avg":2500,"time_avg":15,"stability":0.98}'

# 带基线（不同口径必须显式给出）
python3 scripts/score.py record --skill-id ai-code \
  --metrics-json '{"success_rate":0.9,"accuracy":0.9,"token_avg":2000,"time_avg":12,"stability":0.95}' \
  --baseline-json '{"token_avg":3000,"time_avg":20}'

# 汇总（全部 / 单个）
python3 scripts/score.py report
python3 scripts/score.py report --skill-id ai-code --json

# 指定存储位置
python3 scripts/score.py record --skill-id x --metrics-json '{...}' --store /tmp/scores.json

# 统一入口
python3 scripts/skillmind.py score record --skill-id x --metrics-json '{...}'
python3 scripts/skillmind.py score report --json
```

`report` 输出：`summary`（记录数 / 技能数 / 均分 / 最高 / 最低）、逐技能 `latest`（完整记录，含原始指标）、`avg_score` / `best_score` / `worst_score` / `trend`、`grade_bands` 图例。

退出码：`0` 成功；`1` 指定 `--skill-id` 无记录 / 写入失败；`2` 用法或环境错误（JSON 非法、无子命令）。

## 6. 与其它模块的边界

| 消费方 | 用法 |
|---|---|
| Router | `scores.json` 最新分 → §9.1 的 `0.10 × 历史成功率` 项 |
| `registry_build.py` | 读 `scores.json` 填 `registry.skills[].score`（注册表只读消费） |
| TestMind / Skill Score Report | 用本引擎算分，报告必须同时给 `metrics` + `subscores` + `score`（§7） |

## 7. 反模式

| 反模式 | 为什么错 |
|---|---|
| 只存分数不存原始指标 | 分数掩盖事实，无法复盘为什么掉分 |
| 用 token 绝对值当效率分 | 不同任务不可比；必须用 baseline 比值 |
| 不给 baseline 却报「效率 100」 | 默认基线必须显式标注 `baseline_defaulted` |
| 缺项静默记 0 | 无法区分「真的差」和「没测」 |
| 私自改权重 | 破坏跨技能可比性；改权重 = 改 spec |
| 同输入两次跑出不同分数 | 破坏可复现性；不得引入时间/随机项 |
| `<70` 自动删除 Skill | 违反 §3.4 红线（只降级不删，灾备/事故/迁移类 90 天不用仍是 P0） |
| 只报压缩率 / 只报分数 | §7 / §15 明令禁止 |

## 8. 验收锚点

`tests/scoring-cases.json` 的 8 条用例，容差 ±0.5，覆盖：spec 示例、默认基线、劣于基线、满分上界、下界附近、两位小数、原始指标透传。校验项包括 `score 与 subscores 自洽`、`subscores ∈ [0,100]`、`原始指标全保留`、`baseline_defaulted` 正确。
