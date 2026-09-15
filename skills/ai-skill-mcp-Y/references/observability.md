# observability.md — 遥测与审计（spec-v2 §14.5 / §23）

> 读者=Agent。命中「遥测 / telemetry / 指标 / 告警 / 日志保留 / 脱敏」时读本文件。
> 实现：`scripts/telemetry.py`（标准库，裸 Python 3.9 可跑）；契约：`schemas/telemetry-event.schema.json`。
> 网关侧挂钩见 `gateway.md` §6；脱敏规则见 `security.md` §5。

---

## 1. 定位

| 项 | 内容 |
|---|---|
| 是什么 | 技能运行层的**指标载体**：谁被触发、花了多少 token、成功没有、证据有没有丢 |
| 不是什么 | 不是审计责任链（审计见 `security.md` §2）、不是业务日志、不是 prompt 存档 |
| 落盘 | `<repo>/.skillmind/telemetry.jsonl`（一行一个 JSON，append-only） |
| 命令 | `telemetry.py append` / `telemetry.py summary`（`skillmind.py telemetry ...` 为调度别名） |

**P0 证据永不丢**（spec-v1 §13.3）在遥测上的落点就是 `p0_evidence_retained` 字段：
它是唯一一个「丢了就 Hard Gate FAIL」的指标，`summary` 必须**显式列出**，不允许只报聚合数。

---

## 2. 字段表（spec §14.5，与 `spec-v1.md` §23 一一对应）

| 字段 | 类型 | 必填 | 含义 | §23 对应 |
|---|---|---|---|---|
| `schema_name` | string | 否 | 固定 `skillmind-telemetry-event` | —— |
| `schema_version` | integer | 否 | 当前 `1` | —— |
| `ts` | string(date-time) | **是** | 事件时间，ISO8601 UTC（`Z` 结尾） | —— |
| `session_id` | string | **是** | 会话标识 | `session_id` |
| `agent_id` | string | **是** | 调用方 Agent | `agent_id` |
| `project_id` | string | 否 | 项目标识 | —— |
| `task_id` | string | 否 | 任务标识 | `task_id` |
| `skill_id` | string | **是** | 被调用技能 id | `skill_id` |
| `tool_id` | string | 否 | 被调用 MCP tool | `tool_id` |
| `triggered` | boolean | **是** | 是否真的触发 | `triggered` |
| `trigger_reason` | string | 否 | 命中理由 | `trigger_reason` |
| `context_tokens_loaded` | integer ≥0 | 否 | 载入的上下文 token | `context_tokens_loaded` |
| `result_tokens` | integer ≥0 | 否 | 产出 token | `result_tokens` |
| `call_count` | integer ≥0 | 否 | 本次对该技能/工具的调用次数 | `call_count` |
| `cache_hit` | boolean | 否 | 是否命中缓存 | `cache_hit` |
| `latency_ms` | integer ≥0 | 否 | 端到端延迟毫秒 | `latency_ms` |
| `success` | boolean | **是** | 是否成功 | `success` |
| `rework` | integer ≥0 | 否 | 返工次数 | `rework` |
| `p0_evidence_retained` | boolean | 否 | P0 证据是否保留 | `p0_evidence_retained` |
| `error_class` | string \| null | 否 | 错误分类 | `error_class` |
| `correlation_id` | string | 否 | 跨 Agent/跨 MCP 关联 id | —— |

`required = [ts, session_id, agent_id, skill_id, triggered, success]`
——这六个字段是「能把一次调用说清楚」的下限：何时、哪个会话、谁、用了什么技能、有没有触发、成没成。

`additionalProperties: true`：允许扩展字段（前向兼容），但**扩展字段同样受脱敏管辖**，
不得承载原始敏感值。schema 不用 `additionalProperties: false` 的原因：
拒绝未知字段会让新版本事件无法写入旧版本消费方，把兼容问题变成数据丢失问题。

校验实现说明：`telemetry.py` 自带 draft-07 最小子集校验器（type / required / properties /
additionalProperties / items / enum / const / minimum / maximum / minLength / maxLength /
pattern / format(date-time) / minItems / maxItems / allOf / anyOf / oneOf），
**不引入 `jsonschema` 包**——裸 Python 3.9 环境无第三方依赖。

---

## 3. 落盘格式

```
<repo>/.skillmind/telemetry.jsonl
```

```
{"ts":"2026-09-15T12:00:00Z","session_id":"s1","agent_id":"cursor",...,"p0_evidence_retained":true}
{"ts":"2026-09-15T12:01:00Z","session_id":"s1","agent_id":"cursor",...,"api_token":"***"}
```

约束：

- **一行一个 JSON object**，行内不换行（`json.dumps(..., ensure_ascii=False)`，无 indent）；
- **append-only**：只追加，不原地修改（改历史 = 破坏审计）；
- 写盘前**已完成脱敏**（`--redact` 默认开）；
- 写入前先过 schema 校验，不合规**不落盘**并以退出码 1 报错；
- 坏行（人工编辑、断电截断）不阻断 `summary`：计入 `malformed_lines` 并告警，其余行照常聚合；
- `.skillmind/` 位于**仓根**，不进任何 `artifact_path`，因此**不影响任何 `content_hash`**
  （见 `_common.py:41` 注释）。遥测变化不会制造假 DRIFT。

### 3.1 CLI

```bash
# 追加（校验 → 脱敏 → 追加一行）
python3 scripts/telemetry.py append --event-json '<json>' [--store P] [--no-redact] [--json]

# 聚合（默认读 <repo>/.skillmind/telemetry.jsonl）
python3 scripts/telemetry.py summary [--store P] [--strict] [--json]
```

`--store` 可传目录（自动拼 `telemetry.jsonl`）或 `.jsonl` 文件路径。

退出码：

| 码 | 含义 |
|---|---|
| `0` | 通过（`summary` 默认恒为 0；加 `--strict` 时存在 critical 告警返回 1） |
| `1` | 校验失败（事件不合 schema；`--strict` 下有 critical 告警） |
| `2` | 用法或环境错误（JSON 非法、缺 schema、`--store` 显式指定但不存在） |

---

## 4. summary 指标定义与阈值告警

### 4.1 指标定义

| 指标 | 定义 |
|---|---|
| `total_events` | 可解析的事件条数（坏行不计入，另计 `malformed_lines`） |
| `by_agent` / `by_project` / `by_skill` | 按 `agent_id` / `project_id` / `skill_id` 分组，每组 `{calls, success, success_rate}`；空值归入 `(empty)` |
| `success_rate` | `success == true` 的条数 / `total_events`（**按事件计**，非按调用计） |
| `context_tokens_loaded` | 全量求和（衡量「读了多少」） |
| `result_tokens` | 全量求和（衡量「产出了多少」） |
| `call_count` | 全量求和；`calls_per_event = call_count / total_events`（衡量「一次任务调了几次」） |
| `duplicate_calls` | 同一 `(session_id, agent_id, skill_id, tool_id)` 二次及以后出现的事件条数；明细在 `duplicate_calls_detail`（前 20 条） |
| `cache_hit_rate` | `cache_hit == true` 的条数 / `total_events` |
| `avg_latency_ms` | 有 `latency_ms` 的事件取算术平均；样本数记 `latency_samples` |
| `p0_evidence_lost` | `p0_evidence_retained == false` 的条数；**逐条明细在 `p0_evidence_lost_events`** |
| `rework` | 全量求和（一次没做对的次数） |
| `error_class` | 各错误分类出现次数（成功事件的 `null` 不计入） |
| `alerts` | 命中的告警列表，每条含 `{code, level, value, threshold, message}` |

`duplicate_calls` 的口径说明：它是**同会话内对同一技能/工具的重复调用**的代理指标，
用于发现「重复加载 / 重复调用」（spec-v2 §5 节约优先级第 3 条）。
它不是「同一个技能被用了两次就报错」——不同 session 的调用不算重复。

### 4.2 阈值告警

| code | level | 触发条件 | 为什么 |
|---|---|---|---|
| `P0_EVIDENCE_LOST` | **critical** | `p0_evidence_retained == false` 条数 > 0 | 压缩删了错误证据 = Hard Gate FAIL（spec-v1 §13.3） |
| `SUCCESS_RATE_DROP` | high | `success_rate < 0.90` | 成功率下降是技能退化/误触发的第一信号 |
| `RETRY_STORM` | high | `calls_per_event > 3.0` | 对应网关「5 Agent × 3 retry」重试风暴（`gateway.md` §3） |
| `DUPLICATE_CALLS` | warn | 样本 ≥ 5 且 `duplicate_calls/total > 0.20` | 重复加载/重复调用，浪费 token |
| `LATENCY_HIGH` | warn | `avg_latency_ms > 5000` | 延迟劣化先于成功率劣化 |
| `MALFORMED_LINES` | warn | `malformed_lines > 0` | 落盘被破坏或写入被截断 |

阈值集中在 `telemetry.py:ALERT_THRESHOLDS`，**改这里等于改告警口径**，文档与代码必须同步。
比例类告警设最小样本量（`min_sample_for_ratio = 5`）：2 条事件里 1 条重复算出 50% 是噪声不是信号。

### 4.3 P0 证据丢失的强制呈现

`summary` 无论 `--json` 还是人类可读，都**必须**给出：

1. `p0_evidence_lost` 计数；
2. `p0_evidence_lost_events` 逐条明细（`line` / `ts` / `session_id` / `agent_id` / `skill_id` / `error_class`）；
3. `alerts` 中的 `P0_EVIDENCE_LOST`（level = critical）。

只报「成功率 99%」而隐去「有 1 条 P0 证据丢失」= 用分数掩盖事实（spec-v2 §15 反模式）。

---

## 5. 隐私与脱敏

规则与实现细节见 `security.md` §5，此处只列遥测侧要点：

- **不保存原始敏感输入**（spec-v2 §10 脱敏行）：事件里只写计数、分类、id，不写 prompt / 响应 / 凭证原文。
- 键名命中 `token|key|secret|password|passwd|authorization|cookie|credential` → 整值打码 `***`；
  豁免 `context_tokens_loaded` / `result_tokens`（契约计数指标，非凭证）。
- 值形态命中（`sk-…` / `ghp_…` / `Bearer …` / `AKIA…` / 私钥头 / 长 base64）→ 打码；
  字符串内做子串替换，键名命中做整值替换。
- 脱敏**先于写盘**。`--no-redact` 只关闭**键名规则**（排障时看清字段名），
  **值形态规则恒开**——「禁止原始敏感值落盘」是硬约束，不提供关闭开关。
- 验收方式（可机械执行）：

```bash
grep -c 'sk-' .skillmind/telemetry.jsonl   # 期望 0（原始密钥串不得落盘）
```

- 脱敏命中列表随 `append` 输出（`redacted: ["$.api_token"]`），供审计确认，但**不入事件正文**。

---

## 6. 保留与轮转建议

| 数据 | 保留期 | 方式 |
|---|---|---|
| 遥测事件（常规） | 90 天 | 按天切分 `telemetry-YYYY-MM-DD.jsonl`；单文件 > 32 MB 强制轮转 |
| 遥测事件（压缩） | 90 天内 7 天前的文件 | `gzip`；读取侧需支持 `.jsonl.gz` |
| P0 证据丢失事件 | ≥ 1 年 | 单独抽到 `.skillmind/p0-lost.jsonl` 长期保留（证据优先于存储成本） |
| 审计日志（谁调用/权限变更/blocked 解除） | ≥ 1 年 | 与遥测分离存放，**不可采样** |

原则：

- **证据的保留期不短于指标**。为了省磁盘而先删 P0 证据，是拿 Hard Gate 换存储。
- 轮转不得破坏 append-only 语义：只切新文件，不改旧文件。
- 轮转/清理动作本身要留痕（清理了什么时间段、多少行）。
- 跨项目聚合前先按 `project_id` 过滤：项目数据不得跨项目共享（spec-v2 §6 铁律）。

---

## 7. 自检清单

- [ ] 事件是否带齐 `ts/session_id/agent_id/skill_id/triggered/success` 六个必填字段？
- [ ] `correlation_id` 是否非空（否则无法归因一次任务的多次调用）？
- [ ] 落盘前是否过了 schema 校验（不合规是否**未落盘**且退出码 1）？
- [ ] 落盘前是否已脱敏？grep 原始密钥串是否 0 命中？
- [ ] `summary` 是否同时给出分数**与**原始指标（禁只用分数掩盖事实）？
- [ ] `p0_evidence_retained == false` 是否被**显式逐条列出**？
- [ ] 是否按 `project_id` 隔离聚合，未跨项目合并？

## 8. 反模式（违反即 FAIL）

| 反模式 | 为什么错 |
|---|---|
| 只报成功率/压缩率 | 用分数掩盖事实；丢了证据看不出来 |
| P0 证据丢失只记计数不列明细 | 无法定位、无法复核 |
| 遥测落原始 prompt / token / cookie | 日志成为泄密通道 |
| 原地改历史 jsonl | 破坏 append-only 与审计 |
| 为了省磁盘先删 P0 证据 | 拿 Hard Gate 换存储 |
| 坏行静默跳过不告警 | 数据被截断却当成「一切正常」 |
| 跨项目聚合不按 `project_id` 过滤 | 违反记忆分层铁律 |
