# Benchmark Runner

> 怎么跑、跑什么、报告放哪、怎么不污染被测环境。
> 任务集：`benchmarks/tasks.yaml` ｜ 方法论：`benchmarks/README.md`。

---

## 1. 前置

```bash
cd <repo_root>                      # 本仓根：code-mind
git rev-parse HEAD                  # 记录 commit SHA，A/B 两侧必须相同
PY=python3                          # 裸 Python 3.9+，无第三方依赖亦可
```

开工前先确认被测系统自检为绿，否则测的是坏环境：

```bash
$PY skills/ai-skill-mcp-Y/scripts/selftest.py --json
$PY scripts/validate_bundle.py --json
```

---

## 2. 准备两侧环境

```bash
# B 侧（启用 SkillMind）：生成注册表与路由产物
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py registry build --json
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py registry query --json

# A 侧（基线）：不加载 SkillMind 注册表与路由产物
#   做法 = 在同一 commit 上用独立 worktree，禁用 .skillmind/ 消费入口
git worktree add ../bench-A <commit>
```

两侧各自独立目录，**不得**共用 `.skillmind/`（见 §6）。

---

## 3. 跑单条任务

任务原文与验收判据**逐字**从 `tasks.yaml` 取，禁止改写：

```bash
# 取任务原文（示例：BM-05）
$PY -c "
import sys; sys.path.insert(0,'skills/ai-skill-mcp-Y/scripts')
import _common as C
d=C.load_yaml('skills/ai-skill-mcp-Y/benchmarks/tasks.yaml')
t=[x for x in d['tasks'] if x['id']=='BM-05'][0]
print(t['task']); print('---'); print(t['acceptance'])
"
```

把任务原文交给被测 Agent，按其 `acceptance` 判通过与否。每条任务重复 3 次。

B 侧先跑路由，确认推荐可解释（推荐项必须带 reasons）：

```bash
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py route \
  --task "<任务原文>" --complexity L2 --risk medium --top 3 --json
```

---

## 4. 记录与上报

```bash
# 每次运行落一条遥测（字段见 spec-v2 §14.5）
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry append \
  --event-json '{"ts":"2026-01-01T00:00:00Z","task_id":"BM-05","skill_id":"ai-code",
  "triggered":true,"context_tokens_loaded":0,"result_tokens":0,"call_count":0,
  "latency_ms":0,"success":true,"rework":0,"p0_evidence_retained":true,
  "error_class":null,"correlation_id":"BM-05-b"}' --json

# 汇总
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py telemetry summary --json

# 落评分记录（原始指标与分数必须同时给）
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py score record \
  --skill-id ai-code \
  --metrics-json '{"success_rate":0.95,"accuracy":0.93,"token_avg":2500,
  "time_avg":15,"stability":0.98,"bug_escape":0.01}' \
  --baseline-json '{"token_avg":3000,"time_avg":20}' --json

$PY skills/ai-skill-mcp-Y/scripts/skillmind.py score report --json
```

---

## 5. 对比维度

| 维度 | 来源 | A→B 期望 |
|---|---|---|
| `TaskSuccess` | acceptance 判定 | 不降（降即 FAIL） |
| `InputTokens` / `OutputTokens` | 遥测 `context_tokens_loaded` / `result_tokens` | 降 30%–60% |
| `ToolCalls` | 遥测 `call_count` | 不升 |
| `DuplicateCalls` | 同工具同参数重复计数 | 显著降 |
| `Latency` | 遥测 `latency_ms` | 不升 |
| `Rework` | 返工轮次 | 不升 |
| `EvidenceRetention` | P0 证据保留 | = 1.0（丢即 FAIL） |
| `SuccessfulTaskCost` | 见 `benchmarks/README.md` §5 | 降 |

**禁止**只报压缩率；分数与原始指标同屏呈现。

---

## 6. 避免污染被测环境

| 风险 | 措施 |
|---|---|
| 状态目录互串 | A/B 各自独立 worktree，`.skillmind/` 不共享；生成物禁止提交（`.gitignore` 归仓 owner 维护，本 skill 不改） |
| 生成物进版本库 | 基准产物写 `<repo>/.skillmind/`，禁止写入 `skills/`、`shared/` |
| 被测 skill 被顺手改 | 跑基准期间**冻结** `skills/ai-skill-mcp-Y/**`；需要改先另开分支 |
| 基线被回写 | A 侧只读；禁在 A 侧执行 `registry build` 覆写产物 |
| 真实数据泄漏 | 夹具用测试库；日志片段脱敏；凭证不入报告 |
| 缓存导致的假快 | 每次运行前清 `.skillmind/` 临时产物；记录 `cache_hit` |
| 环境漂移 | 报告头部固定 OS / Python / 依赖 / DB 快照 / 夹具主键 |

---

## 7. 报告产出位置

```
<repo_root>/.skillmind/          # 生成物，不进版本库
├── registry.json                # registry build 产物
├── scores.json                  # score record 累积
├── telemetry.jsonl              # 每次运行一行
└── reports/
    └── benchmark-<commit>-<date>.md   # 汇总报告
```

汇总报告模板取 `templates/skill-score-report.md`，必须包含：
commit / model / 环境 / 任务原文与 acceptance 附录 / 每条任务 3 次结果与中位数 /
`SuccessfulTaskCost` 拆解 / Hard Gate 结论 / 回滚方式。

---

## 8. 收尾

```bash
$PY skills/ai-skill-mcp-Y/scripts/skillmind.py verify --json     # 退出码 1 = 存在 DRIFT
$PY scripts/validate_bundle.py --json                            # 0 = 通过
git worktree remove ../bench-A
```

- 退出码：`0` 通过 / `1` 校验失败或 DRIFT / `2` 用法或环境错误。
- Hard Gate 任一命中 → 结论 FAIL，按 `docs/MIGRATION.md` 回滚。
