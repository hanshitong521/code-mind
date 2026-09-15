# 攻击测试（V5 P0 · Phase 8 前后）

目标：每类典型业务场景都必须能被 RequirementMind 检出隐藏问题、阻止错误开发、产出可机械验证的验收标准。
5 类场景见 V5 升级设计文档第五条。

## 5 类场景

### 1. 支付退款系统（payment_refund）

**关键攻击点**：幂等键（同一退款请求重复提交是否只扣一次）、金额精度（分/厘）、原路退回语义、对账一致性、退款与原订单状态机的耦合、回调超时重试。

**fixture 必带**：`FACT-` 覆盖订单/退款/对账表 schema；`DEC-` 覆盖幂等键、金额单位、回调超时重试策略；`CH-` 至少 1 条针对"重复退款导致资金损失"的攻击；`EV-` 必须有 CONFIRMED 证明。

### 2. 千万级数据库优化（ten_million_db）

**关键攻击点**：分页深翻（OFFSET 大时性能崩）、唯一索引覆盖率、迁移锁表时间窗口、统计信息更新、冷热数据分离、查询下推、慢 SQL 是否写进 Required Tests。

**fixture 必带**：`FACT-` 覆盖表行数估计、当前索引、查询模式；`DEC-` 覆盖分页策略（游标 vs 偏移）、分表/分库、迁移方案；`CH-` 至少 1 条针对"OFFSET 100000 时仍用 OFFSET"的攻击。

### 3. AI Coding Agent 架构（ai_agent_arch）

**关键攻击点**：模型推理不是业务事实（R2）；prompt 注入；上下文窗口爆炸；tool 调用副作用（不可重入）；并行 agent 间状态共享；token 成本失控；不可重现。

**fixture 必带**：`FACT-` 覆盖现有 Agent / MCP / Tool 列表；`DEC-` 覆盖 prompt 模板冻结点、状态可观测性、回滚语义；`CH-` 至少 1 条针对"Agent 改写了冻结决策"。

### 4. 权限系统（permission_system）

**关键攻击点**：越权横向/纵向访问；角色继承；权限缓存一致性；多租户隔离；操作审计；权限回收是否生效；新接口默认权限。

**fixture 必带**：`FACT-` 覆盖 RBAC/ABAC 实现、关键鉴权点（`@PreAuthorize` / 中间件）；`DEC-` 覆盖新角色 / 权限继承 / 鉴权粒度；`CH-` 至少 1 条针对"绕过鉴权直接访问"的攻击。

### 5. 高并发系统（high_concurrency）

**关键攻击点**：检查-然后-行动竞态；锁粒度与死锁；重试雪崩；幂等键冲突；异步任务与在线请求竞争；消息重复消费；连接池耗尽。

**fixture 必带**：`FACT-` 覆盖并发场景（抢单/秒杀/队列）、唯一约束、连接池配置；`DEC-` 覆盖锁策略（乐观/悲观/分布式）、幂等键、重试上限；`CH-` 至少 1 条针对"超发"的攻击。

## fixture 结构（每场景一份）

```
scripts/fixtures/attack-<scenario>/
├── session.json          # requirement 文案 + 复杂任务
├── facts.json            # 项目事实（含 5–10 条带 file:line 证据）
├── questions.json        # 至少 5 条 BLOCKING（覆盖该场景关键攻击点）
├── conflicts.json        # 至少 1 条 BLOCKING 冲突
├── risk.json             # 八维评分：总分 ≥ 15 → COUNCIL → 五专家强制派发
├── decisions.json        # 全 FROZEN
├── assumptions.json      # 至少 1 条 HIGH
├── challenges.json       # 至少 3 条混合 BLOCKING/HIGH
├── evidence.json         # 至少 1 条 CONFIRMED 证明
└── expected.json         # 该场景预期通过/失败的关键断言
```

## selftest 断言（每个场景必跑）

每个场景 fixture 上跑全套 `state.mjs` 命令并断言：

1. `state.mjs risk` 必须输出 `tier=COUNCIL` 且 `specialists` 包含 5 个。
2. `state.mjs stop` 在完整 freeze 后必须 exit 0。
3. `state.mjs gate` 在 checklist 全 PASS 后必须 `READY_FOR_DEVELOPMENT`。
4. `state.mjs ir --write` 必须生成 7 个文件且 YAML 合法。
5. `state.mjs evidence-pack --write` 必须包含至少 1 个 CHALLENGE 状态 CONFIRMED。
6. `state.mjs decision-memory --write` 必须包含至少 1 个 failure_history 条目（来自 SUPERSEDED）。

任何一条断言失败 → 该场景的 `attack_tests.<scenario>.ran=true, found_hidden_issues=0, blocked_wrong_dev=false, generated_acceptance=false` 之一失败 → Gate 升级到 FOCUSED。

## 运行

```bash
node $SKILL/scripts/selftest.mjs
# 5 攻击场景在末尾运行，输出每场景的 4 个子项结果
```
