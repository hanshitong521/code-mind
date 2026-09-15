# ROADMAP — SkillMind Ultimate 开发路线

> 分档依据 `references/spec-v2.md` §12；评分口径 §3.3；验收判据见 `docs/ACCEPTANCE.md`。
> 每档必须**先满足前一档全部判据**才允许进入，禁止跳档宣称。

| Phase | 主题 | 目标分 | 状态 |
|---|---|---|---|
| P0 | 基础：Registry + MCP 接口 + Skill 加载 | 80 | 已交付 |
| P1 | 智能：Router + Score Engine + Token 优化 | 90 | 已交付 |
| P2 | 企业：Gateway + Multi-Agent + Permission + Audit | 95 | 已交付（能力面） |
| P3 | Ultimate：自动进化 + Benchmark + AI 评审 + 自我优化 | 99 | 部分（仅建议侧，未闭环） |

---

## 当前档位（V2.0 本仓实况）

**已完成到 P2。** 本仓 V2.0 已交付的能力面：

| 能力 | 落点 | 对应 Phase |
|---|---|---|
| Registry（注册表机械生成、消费本仓控制面、content_hash 与 `_release_lib` 同语义） | `scripts/registry_build.py` | P0 |
| Router（规则+标签、硬过滤先于打分、推荐带 reasons、Skill Chain） | `scripts/router.py` | P1 |
| Scoring（五维加权、原始指标与分数同屏、默认基线标注 `baseline_defaulted`） | `scripts/score.py` | P1 |
| 三级加载（L0 ≤100 tokens / L1 命中才加载 / L2 执行时单读） | `references/spec-v2.md` §5 + `SKILL.md` 根文档 | P1 |
| Gateway（agent/project/session 隔离、permission 三级、有界重试、correlation_id） | `references/spec-v2.md` §4 + 遥测结构 | P2 |
| 记忆分层（个人/项目/Skill 经验/公共知识，项目数据禁入 Skill 经验） | `references/spec-v2.md` §6 | P2 |
| TestMind 闭环（功能/回归/对抗/Benchmark 四类 + Score Report） | `benchmarks/` + `templates/skill-score-report.md` | P2 |
| 安全（供应链审计 SAFE/REVIEW/BLOCK、脱敏、审计留痕） | `references/spec-v2.md` §10 | P2 |
| 进化（DISCOVER→…→MONITOR，CLASSIFY 七类） | `references/spec-v2.md` §3.4 | P2（治理动作） |

**P3 只完成到哪一步（明确边界）：**

| P3 子项 | 现状 | 红线 |
|---|---|---|
| 自动进化建议 | 已交付：可产出 `OPTIMIZE` / `LAZY-LOAD` / `DISABLE-CANDIDATE` 建议 | 仅建议，不自动执行 |
| patch candidate | 已交付：可产出候选 patch 供人审 | 不自动合入 |
| 进化前测试 | 已交付：候选须过 TestMind 四类测试 | 未过测试不得进入候选 |
| 进化报告 | 已交付：变更前后对比 + 证据 | 禁止只报压缩率 |
| 自动应用 | **未交付** | 禁止自动删除 Skill / 自动改安全权限 / 自动改生产 Tool |
| 高风险无人审批 | **禁止** | 高风险变更必须人工审批 |

> 结论：当前**不得宣称 95+ 生产级**。P2 交付面完整，但「自动升级」仍受 §3.4 红线约束，
> 按 §3.3 分档落在 `90–94 强`。宣称 99 需 P3 全闭环 + 真实任务 A/B 达标（见 ACCEPTANCE）。

---

## P0 基础（目标 80）

| 项 | 内容 |
|---|---|
| 交付物 | `scripts/registry_build.py`（`registry.json`）；`scripts/skillmind.py` 统一 CLI 调度；`shared/capability-registry.yaml` 消费；三级加载的 L0 字段定义 |
| 验收判据 | `registry build` 可机械复现（同输入同输出）；`registry.json` 含 `schema_name/schema_version/skills/rules/mcps/overlap/stats`；每技能 `path` 与 `hash` 真实存在；`source ∈ {release-manifest, filesystem}`；哈希与 `scripts/_release_lib.py` 逐字节一致（无假 DRIFT）；`skills/ai-skill-mcp-Y/scripts/selftest.py` 全绿 |
| 依赖 | 本仓控制面四文件（`shared/release-manifest.yaml`、`shared/capability-registry.yaml`、`shared/schema-versions.yaml`、`deploy.bundle.yaml`）只读可用 |
| 风险 | ① 哈希语义写错 → 假 DRIFT，全仓误报；② 把 `ai-skill-mcp-Y` 误判为 bundled（它不在 `deploy.bundle.yaml` 的 skills 列表）→ 注册表 `bundled` 与分发事实不符 |

## P1 智能（目标 90）

| 项 | 内容 |
|---|---|
| 交付物 | `scripts/router.py`（四级演进，同一时刻只启用一级）；`scripts/score.py`（五维评分）；三级加载预算落地；Token 八级优先序 |
| 验收判据 | 每条推荐带 `reasons`；硬过滤（`blocked` 永不推荐、`deprecated` 仅无替代时推荐并标注、`exclude` 命中记理由）先于打分；评分可复现且 `subscores`/`weights`/`score`/`grade` 齐全；默认基线时输出 `baseline_defaulted: true`；Router 准确率 > 90%（`docs/ACCEPTANCE.md` §2）；无效上下文减少 ≥50% |
| 依赖 | P0 的 `registry.json` 稳定；`shared/capability-registry.yaml` 的 `phases` 提供阶段映射 |
| 风险 | ① 为提召回放宽硬过滤 → `blocked` 技能被推荐（安全 FAIL）；② 打分公式里历史成功率权重过大 → 冷启动技能永不被选（马太效应）；③ 第二套 Router 悄悄出现（违反 §9.4） |

## P2 企业（目标 95）

| 项 | 内容 |
|---|---|
| 交付物 | MCP Gateway 身份/隔离/有界重试；`permission` 三级；审计留痕；`telemetry append/summary`；记忆四层边界；TestMind 四类测试；`benchmarks/` 基准集与 runner；供应链审计评级 |
| 验收判据 | 隔离 100%（agent/project/session 三向不串，见 `docs/ACCEPTANCE.md` §2）；写操作有二次权限检查；Queue/Timeout/Retry 均有界（禁 `5 Agent × 3 retry = 15×` 风暴）；遥测事件字段与 §14.5 一致；四层记忆边界可检查（项目数据不出现在 Skill 经验）；四类测试齐备；≥15 条真实基准任务可解析可执行 |
| 依赖 | P1 的路由与评分产物；`docs/ACCEPTANCE.md` 作为判据唯一入口 |
| 风险 | ① 共享 daemon 缺失 → 每 Agent 冷启动，隔离退化为性能问题；② 遥测写入敏感原文（违反 §10 脱敏）；③ 项目数据被写进 Skill 经验造成跨项目污染 |

## P3 Ultimate（目标 99）

| 项 | 内容 |
|---|---|
| 交付物 | 自动进化闭环（DISCOVER→BASELINE→AUDIT→CLASSIFY→CHANGE→TEST→COMPARE→DEPLOY/ROLLBACK→MONITOR）；AI 评审；自我优化；Benchmark 常态化 |
| 验收判据 | 候选 patch 全流程留痕且可回滚；AI 评审结论必须附原始指标；`CLASSIFY` 七类可机械复现；**红线**：不得自动删除 Skill / 自动改安全权限 / 自动改生产 Tool；高风险变更无人工审批即 FAIL；真实任务 A/B 达标（≥3 真实项目任务 + ≥1 复杂 Debug + ≥1 跨模块，spec-v1 §25） |
| 依赖 | P2 全部判据；稳定的遥测数据量（样本不足时不得宣称）；人工审批通道 |
| 风险 | ① 自动进化把「低频」误判为「无用」而删除灾备/事故/迁移类技能（明令禁止）；② AI 评审自证自洽、无外部判据；③ 进化引入回归但被压缩率数字掩盖 |

---

## 推进规则

1. 每档进入前，先跑 `docs/ACCEPTANCE.md` 的**全部**可勾选项，任一 FAIL 即停在本档。
2. Hard Gate（丢 P0 证据 / 成功率降 / 权限扩大 / 该用找不到）任一命中 → 立即回滚，见 `docs/MIGRATION.md` §4。
3. 分数只作解释，禁止用分数掩盖原始指标（spec-v2 §15）。
4. 禁止跳档：未达 P1 判据不得宣称 P2，未达 P2 判据不得宣称 P3。
