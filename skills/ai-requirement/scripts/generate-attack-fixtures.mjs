#!/usr/bin/env node
// 生成 5 个攻击测试场景 fixture 到 scripts/fixtures/attack-tests/<scenario>/
// 改设计 / 改 selftest 时如需调整 fixture，重跑本脚本即可。
// 运行: node scripts/generate-attack-fixtures.mjs
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, 'fixtures', 'attack-tests');
if (!existsSync(out)) mkdirSync(out, { recursive: true });

const w = (dir, name, data) => {
  const p = join(dir, name);
  writeFileSync(p, JSON.stringify(data, null, 2) + '\n');
};

const dims = (overrides) => {
  // 8 维；overrides 提供 score+refs，缺省 0
  const keys = ['business_criticality', 'data_impact', 'concurrency_risk', 'security_risk', 'compatibility_risk', 'irreversibility', 'blast_radius', 'evidence_gap'];
  const out = {};
  for (const k of keys) out[k] = { score: 0, refs: [] };
  for (const [k, v] of Object.entries(overrides)) out[k] = v;
  return out;
};

const make = (scenario, payload) => {
  const dir = join(out, scenario);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  w(dir, 'session.json', payload.session);
  w(dir, 'facts.json', payload.facts);
  w(dir, 'questions.json', payload.questions);
  w(dir, 'conflicts.json', payload.conflicts);
  w(dir, 'risk.json', { dimensions: dims(payload.riskDims) });
  w(dir, 'decisions.json', payload.decisions);
  w(dir, 'assumptions.json', payload.assumptions);
  w(dir, 'challenges.json', payload.challenges);
  w(dir, 'evidence.json', payload.evidence);
  console.log(`  fixture → fixtures/attack-tests/${scenario}`);
};

// 1. payment_refund — 支付退款系统
make('payment_refund', {
  session: { requirement: '实现支付退款接口（幂等、原路退回、超时重试）', phase: 'GRILLING', updated_at: '2026-09-11T00:00:00.000Z' },
  facts: [
    { id: 'FACT-001', category: 'database', statement: 'orders 表已有 status 字段 tinyint', source: { type: 'sql', path: 'sql/orders.sql', line: 12 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-002', category: 'api', statement: 'POST /api/orders/{id}/refund 已存在', source: { type: 'code', path: 'src/main/java/com/x/RefundController.java', line: 33 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-003', category: 'database', statement: 'refunds 表 amount 字段 decimal(18,2)', source: { type: 'sql', path: 'sql/refunds.sql', line: 8 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-004', category: 'business_rule', statement: '原路退回走 payment-gateway SDK', source: { type: 'doc', path: 'docs/payment-flow.md', line: 22 }, confidence: 0.7, status: 'VERIFIED' },
    { id: 'FACT-005', category: 'test', statement: '现有退款测试仅覆盖成功路径', source: { type: 'test', path: 'src/test/java/com/x/RefundServiceTest.java', line: 41 }, confidence: 1.0, status: 'VERIFIED' },
  ],
  questions: [
    { id: 'Q-001', topic: 'idempotency_key', question: '退款幂等键取哪个？', reason: '决定唯一索引与重复请求判定', priority: 'BLOCKING', options: ['A. order_id', 'B. order_id + reason', 'C. client_request_id', 'D. 沿用现有唯一约束'], recommended_option: 'C', recommendation_reason: 'client_request_id 让客户端可控重试而不依赖服务端语义', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-002', topic: 'amount_unit', question: '退款金额单位？', reason: 'decimal(18,2) 精度限制', priority: 'BLOCKING', options: ['A. 元（2 位小数）', 'B. 分（整数）', 'C. 沿用现订单单位'], recommended_option: 'A', recommendation_reason: 'FACT-003 表结构已定，避免再改', authority: 'TECHNICAL', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-003', topic: 'callback_retry', question: '支付网关回调超时如何重试？', reason: '决定补偿链路', priority: 'BLOCKING', options: ['A. 立即重试 3 次', 'B. 指数退避最多 5 次', 'C. 不重试，靠对账补偿'], recommended_option: 'B', recommendation_reason: '金融接口标准做法', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-004', topic: 'partial_refund', question: '是否支持部分退款？', reason: '决定状态机', priority: 'BLOCKING', options: ['A. 支持，多次累计', 'B. 不支持，全额'], recommended_option: 'A', recommendation_reason: '电商通用需求', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
  ],
  conflicts: [
    { id: 'CON-001', left: '旧 PRD：退款需 1-3 工作日', right: 'docs/adr/008.md：2026-08 起承诺秒级到账', severity: 'IMPORTANT', status: 'OPEN' },
  ],
  riskDims: {
    business_criticality: { score: 3, refs: ['FACT-002'] },
    data_impact: { score: 3, refs: ['FACT-003'] },
    concurrency_risk: { score: 2, refs: ['FACT-001'] },
    security_risk: { score: 2, refs: ['FACT-004'] },
    compatibility_risk: { score: 1, refs: [] },
    irreversibility: { score: 3, refs: ['FACT-003'] },
    blast_radius: { score: 2, refs: ['FACT-002'] },
    evidence_gap: { score: 2, refs: ['FACT-005'] },
  },
  decisions: [],
  assumptions: [
    { id: 'ASM-001', statement: '假设回调超时上限 30s', risk: 'HIGH', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
    { id: 'ASM-002', statement: '假设对账任务每日凌晨执行', risk: 'MEDIUM', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
  ],
  challenges: [
    { id: 'CH-001', claim: '沿用 order_id 唯一索引可防重复退款', challenge: '同笔订单多次部分退款将失败', evidence: ['sql/refunds.sql:8'], counterexample: '订单 #1 第一次退 50，第二次退 30 应允', validation: '核对幂等键 + 多次部分退款语义', severity: 'BLOCKING', status: 'PENDING_VALIDATION' },
    { id: 'CH-002', claim: '回调超时可不重试靠对账', challenge: '对账周期内用户已看到退款但状态未更新', evidence: ['docs/payment-flow.md:22'], counterexample: '用户截图投诉到客服', validation: '查 oncall 历史', severity: 'HIGH', status: 'PENDING_VALIDATION' },
    { id: 'CH-003', claim: 'decimal(18,2) 足以表达退款金额', challenge: '跨境业务可能涉及多币种多精度', evidence: ['sql/refunds.sql:8'], counterexample: '日韩韩元无小数但 BTC 8 位小数', validation: '查业务覆盖币种', severity: 'MEDIUM', status: 'PENDING_VALIDATION' },
  ],
  evidence: [],
});

// 2. ten_million_db — 千万级数据库优化
make('ten_million_db', {
  session: { requirement: '订单列表深翻页性能从 5s 优化到 500ms 以内', phase: 'GRILLING', updated_at: '2026-09-11T00:00:00.000Z' },
  facts: [
    { id: 'FACT-101', category: 'database', statement: 'orders 表当前 4200 万行', source: { type: 'sql', path: 'sql/orders.sql', line: 1 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-102', category: 'database', statement: 'idx_user_created 索引 (user_id, created_at)', source: { type: 'sql', path: 'sql/orders.sql', line: 23 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-103', category: 'api', statement: 'GET /api/orders 接受 page/size 参数', source: { type: 'code', path: 'src/main/java/com/x/OrderController.java', line: 55 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-104', category: 'structure', statement: '历史归档表 orders_archive 已有', source: { type: 'sql', path: 'sql/archive.sql', line: 5 }, confidence: 1.0, status: 'VERIFIED' },
  ],
  questions: [
    { id: 'Q-101', topic: 'pagination', question: '深翻页采用哪种方案？', reason: 'OFFSET 性能瓶颈', priority: 'BLOCKING', options: ['A. 游标分页（created_at, id）', 'B. OFFSET（保持兼容）', 'C. 强制前端禁用深页', 'D. 搜索引擎'], recommended_option: 'A', recommendation_reason: 'OFFSET 100000 性能崩，参考业内做法', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-102', topic: 'archive_threshold', question: '订单保留期多久？', reason: '归档策略', priority: 'BLOCKING', options: ['A. 1 年', 'B. 3 年', 'C. 永久'], recommended_option: 'B', recommendation_reason: '合规要求', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-103', topic: 'search_engine', question: '是否引入 ES？', reason: '成本评估', priority: 'IMPORTANT', options: ['A. 引入', 'B. 不引入，靠 SQL 优化'], recommended_option: 'B', recommendation_reason: '现有 SQL 优化可达成 500ms，无需新组件', authority: 'TECHNICAL', value: 'MEDIUM', status: 'OPEN' },
  ],
  conflicts: [
    { id: 'CON-101', left: '前端：分页必须支持跳页', right: '后端：游标分页无法跳页', severity: 'BLOCKING', status: 'OPEN' },
  ],
  riskDims: {
    business_criticality: { score: 2, refs: ['FACT-101'] },
    data_impact: { score: 3, refs: ['FACT-101'] },
    concurrency_risk: { score: 2, refs: ['FACT-103'] },
    security_risk: { score: 0, refs: [] },
    compatibility_risk: { score: 3, refs: ['FACT-103'] },
    irreversibility: { score: 2, refs: ['FACT-101'] },
    blast_radius: { score: 2, refs: ['FACT-103'] },
    evidence_gap: { score: 1, refs: [] },
  },
  decisions: [],
  assumptions: [
    { id: 'ASM-101', statement: '假设游标分页 UI 可接受', risk: 'HIGH', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
  ],
  challenges: [
    { id: 'CH-101', claim: 'OFFSET + 索引足以达成 500ms', challenge: 'OFFSET 100000 仍需扫描 100000 行', evidence: ['sql/orders.sql:23'], counterexample: '用户翻到第 1000 页', validation: 'EXPLAIN OFFSET 100000', severity: 'BLOCKING', status: 'PENDING_VALIDATION' },
    { id: 'CH-102', claim: '归档表与主表查询性能无关', challenge: '若查询未过滤归档标记会全表扫', evidence: ['sql/archive.sql:5'], counterexample: '老订单的详情查询', validation: '查 SQL 是否带 status 过滤', severity: 'HIGH', status: 'PENDING_VALIDATION' },
  ],
  evidence: [],
});

// 3. ai_agent_arch — AI Coding Agent 架构
make('ai_agent_arch', {
  session: { requirement: '设计 AI Coding Agent OS 平台（多 agent 协同、MCP 协议、状态可观测）', phase: 'GRILLING', updated_at: '2026-09-11T00:00:00.000Z' },
  facts: [
    { id: 'FACT-201', category: 'stack', statement: '现有 Agent 框架：LangGraph + MCP 客户端', source: { type: 'code', path: 'pyproject.toml', line: 12 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-202', category: 'structure', statement: '已有 mcp_servers/ 目录含 5 个 MCP server', source: { type: 'code', path: 'mcp_servers/registry.json', line: 3 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-203', category: 'business_rule', statement: '主 Agent prompt 模板由 PromptMind 管理', source: { type: 'doc', path: 'docs/agent-os.md', line: 18 }, confidence: 0.7, status: 'VERIFIED' },
  ],
  questions: [
    { id: 'Q-201', topic: 'state_share', question: '多 agent 状态如何共享？', reason: '决定架构形态', priority: 'BLOCKING', options: ['A. 共享 Redis', 'B. 各自私有 + Brain 同步', 'C. 事件总线'], recommended_option: 'B', recommendation_reason: 'Brain 是已有组件', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-202', topic: 'tool_safety', question: 'Tool 调用是否可回滚？', reason: '不可重入副作用风险', priority: 'BLOCKING', options: ['A. 全部可回滚（dry-run）', 'B. 只读工具可回滚，副作用不可', 'C. 不回滚，靠校验前置'], recommended_option: 'C', recommendation_reason: '现实约束', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-203', topic: 'token_cost', question: 'Token 成本失控怎么办？', reason: '预算控制', priority: 'IMPORTANT', options: ['A. 硬上限', 'B. 软告警', 'C. 无控制'], recommended_option: 'A', recommendation_reason: '防止成本雪崩', authority: 'USER_ONLY', value: 'MEDIUM', status: 'OPEN' },
  ],
  conflicts: [
    { id: 'CON-201', left: '需求：Agent 可改决策', right: 'R5：冻结决策不可被 Agent 静默覆盖', severity: 'BLOCKING', status: 'OPEN' },
  ],
  riskDims: {
    business_criticality: { score: 3, refs: ['FACT-201'] },
    data_impact: { score: 2, refs: ['FACT-202'] },
    concurrency_risk: { score: 2, refs: ['FACT-201'] },
    security_risk: { score: 2, refs: ['FACT-203'] },
    compatibility_risk: { score: 2, refs: ['FACT-201'] },
    irreversibility: { score: 2, refs: ['FACT-203'] },
    blast_radius: { score: 3, refs: ['FACT-202'] },
    evidence_gap: { score: 2, refs: ['FACT-203'] },
  },
  decisions: [],
  assumptions: [
    { id: 'ASM-201', statement: '假设各 Agent 用同一 LLM API', risk: 'HIGH', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
  ],
  challenges: [
    { id: 'CH-201', claim: 'Agent 可改冻结决策', challenge: '违反 R5，规格不可行', evidence: ['references/freezer.md:40'], counterexample: 'Agent 自作主张改 DEC', validation: '读 R5', severity: 'BLOCKING', status: 'PENDING_VALIDATION' },
    { id: 'CH-202', claim: '共享 Redis 可解决多 Agent 状态', challenge: '脑裂与一致性窗口', evidence: ['docs/agent-os.md:18'], counterexample: '网络分区下两 Agent 写同 key', validation: '查 Redis 集群拓扑', severity: 'HIGH', status: 'PENDING_VALIDATION' },
    { id: 'CH-203', claim: 'Token 硬上限可配置', challenge: '执行到一半超限怎么办', evidence: ['pyproject.toml:12'], counterexample: '已完成 80% 工作的 Agent 超限', validation: '查 abort 语义', severity: 'MEDIUM', status: 'PENDING_VALIDATION' },
  ],
  evidence: [],
});

// 4. permission_system — 权限系统
make('permission_system', {
  session: { requirement: 'RBAC 权限系统新增「部门管理员」角色（跨部门只读 + 本部门写）', phase: 'GRILLING', updated_at: '2026-09-11T00:00:00.000Z' },
  facts: [
    { id: 'FACT-301', category: 'code', statement: '使用 Spring Security + @PreAuthorize', source: { type: 'code', path: 'src/main/java/com/x/SecurityConfig.java', line: 24 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-302', category: 'database', statement: 'role_permissions 表存角色-权限映射', source: { type: 'sql', path: 'sql/rbac.sql', line: 10 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-303', category: 'business_rule', statement: '用户-部门关系存 user_dept 表', source: { type: 'sql', path: 'sql/rbac.sql', line: 30 }, confidence: 1.0, status: 'VERIFIED' },
  ],
  questions: [
    { id: 'Q-301', topic: 'dept_admin_scope', question: '部门管理员可写哪些资源？', reason: '决定权限表达式', priority: 'BLOCKING', options: ['A. 仅本部门用户', 'B. 本部门 + 跨部门只读', 'C. 仅本部门订单'], recommended_option: 'A', recommendation_reason: '最小权限原则', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-302', topic: 'cache_invalidate', question: '权限变更后缓存何时失效？', reason: '避免越权窗口', priority: 'BLOCKING', options: ['A. 立即失效', 'B. 5 分钟', 'C. 1 小时'], recommended_option: 'A', recommendation_reason: '安全优先', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-303', topic: 'audit_log', question: '是否需要审计日志？', reason: '合规', priority: 'IMPORTANT', options: ['A. 全部操作', 'B. 仅敏感操作', 'C. 不需要'], recommended_option: 'A', recommendation_reason: '权限类操作都需审计', authority: 'USER_ONLY', value: 'MEDIUM', status: 'OPEN' },
  ],
  conflicts: [
    { id: 'CON-301', left: '需求：跨部门只读', right: 'RBAC 模型按角色-资源-动作，不支持"角色 + 范围"', severity: 'BLOCKING', status: 'OPEN' },
  ],
  riskDims: {
    business_criticality: { score: 3, refs: ['FACT-301'] },
    data_impact: { score: 2, refs: ['FACT-302'] },
    concurrency_risk: { score: 1, refs: [] },
    security_risk: { score: 3, refs: ['FACT-301'] },
    compatibility_risk: { score: 2, refs: ['FACT-301'] },
    irreversibility: { score: 2, refs: ['FACT-303'] },
    blast_radius: { score: 2, refs: ['FACT-301'] },
    evidence_gap: { score: 1, refs: [] },
  },
  decisions: [],
  assumptions: [
    { id: 'ASM-301', statement: '假设部门嵌套层级 ≤ 3', risk: 'HIGH', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
  ],
  challenges: [
    { id: 'CH-301', claim: '@PreAuthorize("hasRole(... )") 可表达部门范围', challenge: 'SpEL 不支持跨表 user_dept JOIN', evidence: ['src/main/java/com/x/SecurityConfig.java:24'], counterexample: '部门 A 的管理员尝试访问部门 B 资源', validation: '查 AOP 表达式是否带 dept 过滤', severity: 'BLOCKING', status: 'PENDING_VALIDATION' },
    { id: 'CH-302', claim: '权限缓存 5 分钟可接受', challenge: '越权窗口 5 分钟违反合规', evidence: ['src/main/java/com/x/SecurityConfig.java:24'], counterexample: '员工离职后 5 分钟内仍可访问', validation: '查实际缓存 TTL', severity: 'HIGH', status: 'PENDING_VALIDATION' },
  ],
  evidence: [],
});

// 5. high_concurrency — 高并发系统
make('high_concurrency', {
  session: { requirement: '秒杀活动：1 万件商品 10 万 QPS 不超发', phase: 'GRILLING', updated_at: '2026-09-11T00:00:00.000Z' },
  facts: [
    { id: 'FACT-401', category: 'database', statement: 'seckill 表有 (sku_id, user_id) 唯一索引', source: { type: 'sql', path: 'sql/seckill.sql', line: 12 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-402', category: 'api', statement: 'POST /api/seckill/{sku_id}/buy 已有', source: { type: 'code', path: 'src/main/java/com/x/SeckillController.java', line: 18 }, confidence: 1.0, status: 'VERIFIED' },
    { id: 'FACT-403', category: 'structure', statement: 'Redis Cluster 6 节点已部署', source: { type: 'config', path: 'application.yml', line: 34 }, confidence: 1.0, status: 'VERIFIED' },
  ],
  questions: [
    { id: 'Q-401', topic: 'deduct_strategy', question: '库存扣减采用？', reason: '超发防御', priority: 'BLOCKING', options: ['A. Redis 预扣 + 异步落库', 'B. DB 乐观锁', 'C. DB 悲观锁', 'D. 分布式锁'], recommended_option: 'A', recommendation_reason: '10 万 QPS DB 撑不住', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-402', topic: 'queue_overflow', question: '超出库存的请求如何处理？', reason: '决定前端反馈', priority: 'BLOCKING', options: ['A. 立即返回已售罄', 'B. 入队等待', 'C. 概率放行'], recommended_option: 'A', recommendation_reason: '用户体验清晰', authority: 'USER_ONLY', value: 'HIGH', status: 'OPEN' },
    { id: 'Q-403', topic: 'retry_policy', question: '消息队列消费失败如何重试？', reason: '防止消费丢失', priority: 'IMPORTANT', options: ['A. 最多 3 次指数退避', 'B. 不重试', 'C. 进死信队列'], recommended_option: 'A', recommendation_reason: '常规做法', authority: 'TECHNICAL', value: 'MEDIUM', status: 'OPEN' },
  ],
  conflicts: [
    { id: 'CON-401', left: '需求：1 万件', right: '现状：seckill.stock 字段可能并发更新', severity: 'BLOCKING', status: 'OPEN' },
  ],
  riskDims: {
    business_criticality: { score: 3, refs: ['FACT-402'] },
    data_impact: { score: 3, refs: ['FACT-401'] },
    concurrency_risk: { score: 3, refs: ['FACT-402'] },
    security_risk: { score: 1, refs: [] },
    compatibility_risk: { score: 1, refs: [] },
    irreversibility: { score: 3, refs: ['FACT-401'] },
    blast_radius: { score: 2, refs: ['FACT-402'] },
    evidence_gap: { score: 1, refs: [] },
  },
  decisions: [],
  assumptions: [
    { id: 'ASM-401', statement: '假设 Redis 原子操作 DECR 不会超发', risk: 'HIGH', source: 'MODEL_INFERENCE', status: 'UNVERIFIED' },
  ],
  challenges: [
    { id: 'CH-401', claim: 'DB 乐观锁可防超发', challenge: '10 万 QPS 下 DB 锁等待是瓶颈', evidence: ['sql/seckill.sql:12'], counterexample: '活动开始瞬间 DB 锁队列爆', validation: '压测验证', severity: 'BLOCKING', status: 'PENDING_VALIDATION' },
    { id: 'CH-402', claim: 'Redis DECR 一定不会超发', challenge: '异步落库失败时库存已减但 DB 未扣', evidence: ['application.yml:34'], counterexample: 'Redis 减到 0 但 DB 还有 1 个', validation: '查异步落库重试幂等', severity: 'HIGH', status: 'PENDING_VALIDATION' },
  ],
  evidence: [],
});

console.log('\n=> 5 个攻击测试场景 fixture 已生成到 scripts/fixtures/attack-tests/');
