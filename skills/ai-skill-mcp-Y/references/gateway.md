# gateway.md — MCP 网关与多 Agent 共享（spec-v2 §4）

> 读者=Agent。命中「多 Agent / MCP 共享 / 工具暴露 / 重试风暴 / 降级」时读本文件。
> 上位规格：`spec-v2.md` §4（网关）、§9.4（唯一权威路由）、§14.1（CLI）、§14.5（事件）；
> 方法论来源：`spec-v1.md` §9（大能力小暴露）、§15（多 Agent 共享 MCP）、§15.1（Fail-safe）。

---

## 0. 边界（先钉死，防越界）

| 项 | 内容 |
|---|---|
| 网关做什么 | 身份识别、隔离、工具暴露、有界重试、降级、留痕 |
| 网关不做什么 | 不做业务逻辑；不做第二套 Router（§9.4）；不改写注册表/控制面文件 |
| 权威来源 | 路由结果只由 SkillMind Router 产出；网关只**消费**它决定暴露哪些工具 |
| 越界信号 | 网关开始「猜」该用哪个 skill、开始写 `.skillmind/registry.json`、开始改 `shared/*.yaml` |

**SkillMind 只做「选」。** 网关是「选」的执行面（暴露多少工具、重试几次），不是决策面。

---

## 1. 五个身份字段（P0，缺一即不可审计）

每个 MCP 请求必须携带以下字段；缺失后果直接对应 spec-v2 §4 表。

| 字段 | 取值 | 作用 | 缺失后果 | 落点 |
|---|---|---|---|---|
| `agent_id` | cursor / claude-code / codex / local | 区分调用方 Agent | 记忆污染 | telemetry 事件必填 |
| `project_id` | 项目标识（同仓稳定） | 区分项目 | 项目串数据 | telemetry 事件 |
| `session_id` | 会话标识 | 区分会话 | 上下文串味 | telemetry 事件必填 |
| `permission` | `read` / `execute` / `admin` | 越权拦截 | 越权执行 | 审计日志（不入事件正文） |
| `logging` | 调用留痕开关（默认开） | 可追溯 | 无法审计 | 审计日志 |

补充强制字段：

- `correlation_id`：一次请求跨 Agent / 跨 MCP 的唯一关联 id，必须随请求透传并写入 telemetry 事件（§14.5）。
  没有它，「一次任务为什么调了 12 次」无法归因，重试风暴无法定位。
- `task_id`：同一任务的多次调用共用；用于把事件串成一次任务的全生命周期。

**`permission` 与 `logging` 不进 telemetry 事件正文**（事件 schema 无此二字段），
它们进审计日志。原因：事件是**指标载体**，审计日志是**责任载体**，两者保留期不同（见 `observability.md` §6）。

---

## 2. 四类隔离要求（P0）

| # | 要求 | 反例（禁） | 落地判据 |
|---|---|---|---|
| I1 | 共享 daemon，禁每 Agent 冷启动 | 5 个 Agent 各拉一份 MCP，各自加载 registry | 同一 host 上 MCP 进程数 ≤ 1（按 project 隔离时按 project 计） |
| I2 | 禁全局可变 task state | 模块级 `CURRENT_TASK = ...` 被并发覆盖 | 请求级上下文随请求传递；跨请求共享的只有只读快照 |
| I3 | 请求必须带 `correlation_id` | 只靠时间戳关联 | 事件中 `correlation_id` 非空率 = 100% |
| I4 | 写操作显式隔离 + 二次权限检查 | 读写工具同一入口、同一权限 | Write/Destructive 层独立入口，`permission ∈ {execute, admin}` 且二次确认 |

隔离失效的代价是**乘法**不是加法：一个被污染的 session 会把错误上下文写进项目记忆，
再由 Brain 扩散到后续所有任务。

### 2.1 状态分层（谁可变）

```
请求级（可变，随请求销毁）  → 参数、临时句柄、correlation 上下文
会话级（可变，session 内共享）→ 已加载技能集合、预算余量
全局级（只读，进程启动装载） → registry.json 快照、capability-registry、schema-versions
```

全局级**只读**是硬约束：网关不得在运行时改注册表。要改注册表 = 走离线 `registry build`。

---

## 3. 有界 Queue / Timeout / Retry（防重试风暴）

### 3.1 为什么必须有界

无界时的最坏情况：

```
5 Agent × 每请求 3 retry = 15 次并发重试
再叠加每个 Agent 客户端自身的重试（通常再 ×2） → 30 次
下游 MCP 已过载 → 全部超时 → 客户端继续重试 → 雪崩
```

关键点：**重试是并发放大器**。单 Agent 时看不出来，多 Agent 时是乘数。

### 3.2 边界值（默认，可在 task bundle 显式收紧，禁止放宽）

| 维度 | 默认值 | 说明 |
|---|---|---|
| Queue 深度 | 32 | 超出立即返回「忙」，**不排队堆积**（排队会把超时变成不可预测） |
| 单次调用 Timeout | 读类 30s / 写类 120s | 写类给长事务留时间，但不无限 |
| 单请求 Max Retry | 3（**仅幂等读**） | 写类 **max_retry = 0**，重试 = 重复写 |
| 全局重试预算 | 6 次 / 10s 窗口 | 令牌桶；超预算的新重试直接走降级链，不进入重试 |
| 退避 | `200ms × 2^n + jitter` | 总退避预算 ≤ 5s；jitter 防同步重试共振 |
| 单请求总时长上限 | 读 90s / 写 300s | 到顶即失败，给出证据，不静默挂住 |

全局重试预算把最坏情况从 15 次压到 6 次（降 60%），且**预算是全局的**，
任一 Agent 无法通过增加自身重试次数挤占其他 Agent。

### 3.3 重试判据（三条同时满足才重试）

1. 工具**幂等**（只读或带幂等键）；
2. 错误类别**可恢复**（`Timeout` / `ConnectionReset` / `RateLimited`）；
3. 全局重试预算未耗尽。

不满足任一条 → 直接进入 §5 降级链。`PermissionDenied` / `SchemaViolation` / `InvalidArgument`
**永不重试**（重试只会重复同一次错误，并污染 telemetry 的 error_class 分布）。

---

## 4. 工具四层分层与暴露预算

### 4.1 四层（spec-v2 §4 / spec-v1 §9.1）

| 层 | 内容 | 默认可见性 | 最低权限 | 例 |
|---|---|---|---|---|
| Core / Discovery | 少量只读治理能力 | 常驻 | `read` | `registry query`、`route`、`telemetry summary` |
| Domain Tools | 按任务域的工具 | 命中 phase 才暴露 | `read` | 代码结构定位、项目记忆检索、测试执行 |
| Write / Destructive | 写文件、改配置、DB write | **默认隐藏**，需显式写意图 | `execute` + 二次确认 | 写文件、改规则、DB write |
| Deep / Expensive | 高成本能力 | **默认隐藏** | `admin` 或显式声明 | 全仓扫描、benchmark、embedding 重建 |

暴露顺序即加载顺序：`Core → Domain → Write → Deep`，逐级放宽，逐级加权限。

### 4.2 最小充分集

```
单任务最小充分集常见 3–8 个，非硬顶
```

- 这是**经验区间**，不是硬编码上限；硬顶由 §4.3 的 `tool_budget` 决定。
- 判据不是「数量少」，而是**最小充分**：少一个就做不成，多一个就是浪费。
- 反模式：一次性暴露全部工具（spec-v2 §15「一次暴露全部 tool」）→ 模型选择成本上升，误选率上升。

### 4.3 与本仓 `capability-registry.yaml` 的对接

**契约来源**：`shared/capability-registry.yaml` 的 `tool_budget` 段（只读消费，禁改写）。

```yaml
tool_budget:
  default_max_tools_per_phase: 12
  note: "超出须在 task bundle 中显式声明理由"
```

对接算法：

```
phase 暴露上限 = tool_budget.default_max_tools_per_phase          # 12
实际暴露集     = Core 常驻集 ∪ capabilities[phases[phase]].*       # 按 phase 取能力
若 |实际暴露集| > phase 暴露上限:
    必须在 task bundle 显式声明理由，否则裁剪 Domain 层，保留 Core
```

当前注册表各 phase 的能力数（`phases` 段，合法 phase 取自 `validate_bundle.py:VALID_PHASES`）：

| phase | 能力数 | 是否触发预算 |
|---|---|---|
| `requirement` | 4 | 否 |
| `design` | 3 | 否 |
| `coding` | 5 | 否 |
| `debug` | 4 | 否 |
| `verification` | 4 | 否 |
| `review` | 1（`lean.review`，Overlay） | 否 |
| `all` | 常驻（`context.fetch`） | 否 |

结论：**当前注册表下预算不绑定**（最大 5 ≪ 12）。预算的价值在技能/工具规模上来后兜底，
以及作为「不得一次性全暴露」的机器可校验上界。

### 4.4 不得新增 owner

`capability-registry.yaml` 的 `owner` 必须 ∈
`{requirement-mind, project-brain-agent, token-mind, test-mind, concise-mind, ai-programming-docs, git}`
（见 `scripts/validate_bundle.py:35`）。**SkillMind 是 skill，不是能力 owner**，
因此网关与路由**不得**向 `capabilities` 新增 `owner: skillmind` 条目——那会让 `validate_bundle.py` 报错。
网关只消费 `phases` 与 `tool_budget`，不参与归属声明。

---

## 5. Fail-safe 降级链（禁静默降级）

```
MCP unavailable / 调用失败
  ↓
1 快速探测：1 次，≤2s，不重试（探测本身也重试 = 放大故障）
  ↓
2 一次有限重连（仅当 §3.3 三条判据全满足）
  ↓
3 可降级则降级：
    只读类 → 用 registry.json 本地快照 + 上次路由结果
    上下文类 → 缩小上下文，标注「上下文不完整」
    工具类 → 返回「无可用工具」+ 明确原因
  ↓
4 不可降级则给明确证据并停止：
    correlation_id + 错误原文 + error_class + 已尝试次数 + 建议动作
```

**红线**：

- 禁无限重试 / 无限等待；
- 禁静默降级——降级必须在输出中显式声明（`spec-v2 §15`：静默降级 = STOP）；
- 降级后仍须保证 P0 证据保留（`p0_evidence_retained` 不得因降级置 false）；
- 降级事件必须写入 telemetry，`error_class` 记录降级原因，供 `summary` 统计降级率。

---

## 6. 遥测挂钩（网关 → telemetry）

网关每次调用产出**一条** telemetry 事件（`schemas/telemetry-event.schema.json`）：

| 事件字段 | 网关来源 |
|---|---|
| `session_id` / `agent_id` / `project_id` / `task_id` | 身份字段（§1） |
| `correlation_id` | 请求透传 |
| `skill_id` / `tool_id` | 路由结果 + 实际调用 |
| `triggered` / `trigger_reason` | 路由是否命中及理由 |
| `call_count` | 本任务对该工具的调用次数（受 §3.2 上限约束） |
| `cache_hit` | 是否命中缓存（未重复加载） |
| `latency_ms` | 端到端延迟 |
| `success` / `error_class` / `rework` | 结果与错误分类 |
| `p0_evidence_retained` | 证据保留判定（Hard Gate） |

落盘命令（`--store` 省略即 `<repo>/.skillmind/telemetry.jsonl`）：

```bash
python3 scripts/telemetry.py append --event-json '<json>'
python3 scripts/telemetry.py summary --json
```

**脱敏在落盘前完成**（默认开启，见 `observability.md` §5）：
网关**不得**把原始 prompt、原始响应、token、cookie 塞进事件；只写计数与分类。

---

## 7. 自检清单

- [ ] 请求是否带齐 `agent_id` / `project_id` / `session_id` / `permission` / `logging` / `correlation_id`？
- [ ] 全局级状态是否只读（无运行期改注册表）？
- [ ] Queue / Timeout / Retry 是否全部有界，且重试预算是否**全局**而非每 Agent？
- [ ] 写类工具是否独立入口 + `execute` 权限 + 二次确认 + `max_retry = 0`？
- [ ] 暴露工具数是否 ≤ `tool_budget.default_max_tools_per_phase`，超出是否在 task bundle 声明理由？
- [ ] 降级是否显式声明（无静默降级）？P0 证据是否仍保留？
- [ ] 本次调用是否产出遥测事件，且落盘前已脱敏？

## 8. 反模式（违反即 FAIL）

| 反模式 | 后果 |
|---|---|
| 每 Agent 冷启动一份 MCP | 加载抖动 + 注册表多份不一致 |
| 全局可变 task state | 并发串味，错误上下文进项目记忆 |
| 重试次数写在 Agent 侧且无全局预算 | 5 × 3 = 15× 重试风暴 |
| 写类工具自动重试 | 重复写、重复扣减、重复发消息 |
| 一次性暴露全部工具 | 选择成本上升，误选率上升 |
| 静默降级 | 用户以为成功，实际无工具可用 |
| 网关自建 Router | 违反 §9.4 唯一权威路由 |
