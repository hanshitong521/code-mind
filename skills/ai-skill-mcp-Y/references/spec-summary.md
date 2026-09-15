# SkillMind V2.0 摘要（日常够用; 全文 spec-v2.md; V1 审计方法论见 spec-v1.md）

原则: 能力做大, 入口做小; 精准触发, 按需展开; 关键证据永不丢。
优先级不可颠倒: 正确率 → P0证据 → 安全 → token → tool次数 → 延迟 → 维护 → 扩展。

五层栈边界(禁双开): RequirementMind=WHAT · Brain=WHY · TokenMind=CTX · SkillMind=HOW-选 · ai-code/ai-design=HOW-做 · TestMind=VERIFY · Evidence Gate=证据。
SkillMind 只做「选」不做「做」; 运行时权威 Router 只有一处; 本仓控制面只读消费, 禁反向改写。

## V2 模块一览

| 模块 | 做什么 | 红线 |
|---|---|---|
| Registry | 每技能一条: id/category/tags/version/status/score/owner/load_mode/risk/destructive/triggers; 状态机 draft→testing→verified→deprecated, blocked 只能人工解 | deprecated 不删除(灾备/事故/迁移 90 天不用仍 P0) |
| Router | 输入任务原文/项目类型/L0-L3/风险/历史; 输出推荐(带置信+理由)+执行链+排除项与理由; 四级演进同一时刻只启用一级 | 硬过滤先于打分; 禁第二套 Router |
| Scoring | 成功率40%+准确率30%+Token效率15%+速度10%+稳定性5%; 原始指标与分数同屏; 默认基线须标 baseline_defaulted | 禁分数掩盖事实 |
| Gateway | agent_id/project_id/session_id/permission/logging; 共享 daemon; Queue/Timeout/Retry 均有界; 失败降级不无限卡 | 禁 5×3=15× 重试风暴 |
| 三级加载 | L0 name+短desc+tags+score ≤100 tokens; L1 SKILL.md 命中才加载; L2 scripts/examples/references 执行时单读 | 无效上下文需降 ≥50% |
| 记忆分层 | 个人/项目/Skill经验/公共知识四层; candidate→verified→stale/deprecated | 项目数据禁入 Skill 经验 |
| TestMind | 功能/回归/对抗/Benchmark 四类; 报 TaskSuccess+Tokens+ToolCalls+DupCalls+Latency+Rework+EvidenceRetention | 禁只报压缩率 |
| 进化 | DISCOVER→BASELINE→AUDIT→CLASSIFY→CHANGE→TEST→COMPARE→DEPLOY/ROLLBACK→MONITOR; CLASSIFY 七类 | 禁自动删 Skill / 改权限 / 改生产 Tool; 高风险须人工审批 |
| 安全 | read/execute/admin 三级; destructive 二次确认; 供应链审计 SAFE/REVIEW/BLOCK; 遥测脱敏 | 高 Star ≠ 可信 |

## Token 八级优先序

不加载 → 不重复加载 → 不重复调用 → 缓存复用 → 增量读取 → 结构化筛选 → 摘要 → 深度压缩。
最省 token 的内容, 是根本没必要进上下文的内容。

## 评分公式

Score = 成功率×0.40 + 准确率×0.30 + Token效率×0.15 + 速度×0.10 + 稳定性×0.05
Token效率 = clamp01(baseline_token_avg / token_avg); 速度 = clamp01(baseline_time_avg / time_avg)。
分档: 95-100 生产级 | 90-94 强 | 80-89 可用待优化 | 70-79 上线前复查 | <70 重设计或禁用。

## 反模式（违反即 FAIL）

万能 Skill · description 写满工作流 · 根 SKILL.md 塞尽参考资料 · 一次暴露全部 tool · 只看压缩率 · 多层都做 Router · 每任务跑全部测试 · 自动删除低频 Skill · 分数掩盖原始指标。

## 闸门与命令

Hard Gate(任一 FAIL): 丢P0证据 | 成功率降 | 权限扩大 | 该用找不到(Recall崩)。
上线门槛: 正确/证据/安全 Gate PASS + 无新增严重冲突 + trigger 四类测试 + 回滚方式明确 + ≥3 真实任务 A/B。
命令: `skillmind.py registry build|query · route · score record|report · telemetry append|summary · manifest validate · verify · selftest`（详见 README.md）。
验收表: docs/ACCEPTANCE.md ｜ 路线: docs/ROADMAP.md ｜ 迁移: docs/MIGRATION.md ｜ 基准: benchmarks/tasks.yaml。

## 审计方法论（V1 保留）

V1 定审计方法论, V2 定平台形态, 互补不互斥。
治理不取代: RequirementMind(What) · Brain(Know) · TokenMind(See) · Skills/MCP(Do) · TestMind(Verify)。
审计 = 发现浪费/冲突/误触发, 给可验证改法; 流程 G0 定范围 → G1 inventory → G2 四类 trigger → G3 分类 KEEP|OPTIMIZE|MERGE|SPLIT|LAZY-LOAD|DISABLE-CANDIDATE|BLOCK → G4 填报告 → G5 一次一资源改 → G6 复跑 trigger, FAIL 则回滚该资源。
Skill 根=路由器; MCP=大能力小暴露; AGENTS=导航不是清单。默认最小: 先报告后改, 用户说「直接改」才动文件。
评分仅作解释, 禁止用分数掩盖原始指标; V1 的 100 分用于审计结论, V2 的五维分用于技能评分, 禁混用同一数字。
细节 SSOT: spec-v1.md §18 评分 / §19 生命周期 / §22 反模式 / §24 Benchmark / §25 上线门槛 / §28 DoD。
