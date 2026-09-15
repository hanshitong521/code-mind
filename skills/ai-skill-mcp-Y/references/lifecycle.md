# 进化生命周期

> 规格：`references/spec-v2.md` §3.4 ｜ 方法论：`references/spec-v1.md` §19 自动治理生命周期 ｜ 验证：`references/testmind.md` ｜ 日志：`templates/evolution-log.md`
> 范围：Skill / MCP / Rules 三类资源同一套生命周期；**离线或准实时**执行，运行时只消费产物（`registry.json` + 路由结果）。

## 0 一条红线

**禁止自动删除。** 系统可自动产出 `DISABLE-CANDIDATE`，但不得自动删除 Skill、不得自动改安全权限、不得自动改生产 Tool（V1 §19.1、`references/spec-v2.md` §3.4）。

## 1 九相生命周期

```
DISCOVER → BASELINE → AUDIT → CLASSIFY → CHANGE → TEST → COMPARE → DEPLOY/ROLLBACK → MONITOR
                                                                    ↑____________|
                                                              （MONITOR 回流 CLASSIFY）
```

| 相 | 输入 | 动作 | 出口物 | 禁 |
|---|---|---|---|---|
| DISCOVER | 仓根、已装 skill 目录、MCP 清单、rules | 盘点资源与重叠面（`references/inventory.md` / `scripts/inventory.py --root R`） | 资源清单 + 重叠图 | 只看新资源不看存量 |
| BASELINE | 资源清单 | 跑基线任务集，记原始指标与分数 | `baseline metrics`（八项，`references/testmind.md`） | 无基线就改 |
| AUDIT | 单资源 + 基线 | 按 §2 判据逐项审计（trigger / 尺寸 / 重叠 / 证据 / 安全） | 审计发现（`templates/audit-report.md`） | 只给分数不给原始指标 |
| CLASSIFY | 审计发现 | 落入七态之一（§2） | 每资源一个分类结论 + 理由 | 一个资源多结论 |
| CHANGE | 分类结论 | **一次一资源**按 `references/apply.md` 改 | 改动清单 | 一次改多个资源；顺手改相邻内容 |
| TEST | 改动 | 四类测试 + trigger 四类（`references/testmind.md`） | 测试记录 | 跳过对抗测试 |
| COMPARE | 测试记录 | 同任务 A/B，五固定项 | A/B 对比表 | 不固定 commit/model/输入/判据/环境 |
| DEPLOY / ROLLBACK | A/B 结论 | 过门槛则上线（旧版标 `deprecated` **不删**）；否则回滚 | 新版本 + 回滚点 | 无回滚点上线上线；删除旧版 |
| MONITOR | 上线后遥测 | 跟踪八指标、误触发、冲突、`rework` | 回流信号 → CLASSIFY | 上线后不观察 |

## 2 CLASSIFY 七态

| 态 | 判据 | 动作 | 状态机联动 |
|---|---|---|---|
| `KEEP` | 无高价值问题；低频但属灾备/事故/迁移/安全类 | 不动 | 保持现状态 |
| `OPTIMIZE` | trigger 偏宽/偏窄、根文档过大、description 写工作流 | 按 `references/apply.md` 改配方，一次一资源 | `verified` 保持；改动期可置 `testing` |
| `MERGE` | 两资源职责重叠，`shared_tags` 高且场景重合 | 留一个赢家，输家 description 改 Deprecated 指向赢家 | 输家 → `deprecated`（不删） |
| `SPLIT` | 一个资源覆盖多个不相关场景、根文档超限 | 拆成两个，各写清 `Use when` / `Not for` | 新资源 → `draft` |
| `LAZY-LOAD` | 高频入口塞了重内容；或重内容只在少数场景用 | 移入 L2，路由表写「命中才读哪一条」 | `load_mode: deep` / `on-demand` |
| `DISABLE-CANDIDATE` | 长期零命中 + 无独有能力 + 有替代 | **仅产出候选**，人工确认后才可 `deprecated` | 保持 `verified` 直到人工裁决 |
| `BLOCK` | 安全/合规问题（越权、泄密、隐藏 telemetry、prompt injection） | 一票否决，立即停用 | `blocked`（**只能人工解除**） |

**禁**：把 `DISABLE-CANDIDATE` 直接当删除指令执行；把 `BLOCK` 自动降级为其他态。

## 3 禁止自动删除：低频 ≠ 可删

以下类别 **90 天不用仍是 P0**，必须 `KEEP`：

| 类别 | 例子 |
|---|---|
| 灾备 | 主备切换、数据恢复、集群重建 |
| 生产事故处理 | 线上回滚、熔断解除、紧急限流 |
| 安全事件 | 凭证轮换、入侵排查、权限回收 |
| 大版本迁移 | 框架升级、DB 大版本迁移、数据迁移 |

判定句：**「出事那天，没有它会不会更慢/更危险？」** 会 → `KEEP`，哪怕命中率为 0。

`deprecated` 的语义是**降级可见性**（不推荐、仅无替代时标注推荐），**不是删除**；删除只能由人工在离线备份后执行。

## 4 Skill 状态机与评分联动

```
draft ──▶ testing ──▶ verified ──▶ deprecated
  │           │            │            │
  └───────────┴────────────┴────────────┴──▶ blocked（安全/合规一票否决，只能人工解除）
```

| 状态 | 进入条件 | 评分联动 | 路由行为 |
|---|---|---|---|
| `draft` | 新建/SPLIT 产出 | 无记录 → `score: null` | 不参与推荐 |
| `testing` | 改动中 / 待验证 | 记候选分，标注 `baseline_defaulted` | 仅显式点名可用 |
| `verified` | 上线门槛七项 PASS（`references/testmind.md` §4） | 写入正式分数；与原始指标同时展示 | 正常参与路由 |
| `deprecated` | MERGE 输家 / 人工确认的 DISABLE-CANDIDATE | 分数冻结并标注原因 | 仅无替代时推荐且标注 |
| `blocked` | 安全/合规 FAIL | 分数置空并标 `blocked` | **永不推荐** |

分档（`references/spec-v2.md` §3.3）：`95–100 生产级` / `90–94 强` / `80–89 可用待优化` / `70–79 上线前复查` / `<70 重设计或禁用`。

联动规则：

- 分数跌破所在档位下限 → 自动回流 `CLASSIFY`（至少产出 `OPTIMIZE`），**禁**自动改状态为 `deprecated`。
- `blocked` 不被任何自动降级覆盖。
- 状态变更必须与评分记录同批写入，避免「状态新、分数旧」的假象。

## 5 进化日志（记录什么）

每次 CHANGE→COMPARE 必须留一条，落点 `templates/evolution-log.md`：

| 字段 | 内容 |
|---|---|
| 版本 | 改前 → 改后（`skill.yaml.version`） |
| 日期 | 改动与验证日期 |
| 触发原因 | 来自哪一相（DISCOVER 发现 / MONITOR 回流 / 用户报错 / 冲突告警） |
| 改动 | 一次一资源的改动清单（改了什么、删了什么、移入哪个 L2） |
| 评分前后 | 分数 + **原始八指标前后值**（禁只写分数） |
| A/B 结果 | 五固定项 + 重复次数 + 八指标对比 + Verdict |
| 回滚点 | 改前路径 / git ref / 旧版目录位置 |

**禁**：日志只写「优化了 description」这类无判据描述；禁只写分数不写原始指标；禁省略回滚点。

## 6 MONITOR 回流信号

| 信号 | 阈值 | 回流动作 |
|---|---|---|
| 误触发上升 | `Misfire Rate` 上升 | `OPTIMIZE`（改窄 description / `exclude`） |
| 该用找不到 | `Recall` 下降 | `OPTIMIZE`（补 `trig:` / tags） |
| 重复调用 | `DuplicateCalls` 上升 | 查 MCP 去重与 retry 边界 |
| 返工上升 | `Rework` 上升 | 优先怀疑证据丢失，回 `references/testmind.md` §5 |
| 新增重叠 | `registry.json.overlap.severity` 升高 | `MERGE` 或改窄 |
| 长期零命中 | 见 §3 判定句 | `KEEP` 或 `DISABLE-CANDIDATE`（人工裁决） |

## 7 检查表

- [ ] 九相齐全，且每相有出口物
- [ ] CLASSIFY 每资源**恰好一个**结论，且属七态之一
- [ ] `DISABLE-CANDIDATE` 未经人工确认未被降级为删除
- [ ] 灾备/事故/迁移/安全类资源未被判 `DISABLE-CANDIDATE`
- [ ] `blocked` 未被自动覆盖
- [ ] CHANGE 一次一资源；`references/apply.md` 配方已遵循
- [ ] TEST/COMPARE 结果满足上线门槛七项
- [ ] 状态机变更与评分记录同批写入
- [ ] 进化日志七字段齐全（含回滚点与原始指标）
- [ ] 旧版本标 `deprecated` 保留，未删除

## 8 STOP

STOP:自动删除 skill|把 DISABLE-CANDIDATE 当删除令|自动改安全权限|自动改生产 tool|blocked 被自动降级|灾备/事故/迁移/安全类判禁用|一个资源多结论|一次改多资源|无基线就改|无回滚点上线|上线后不监控|删旧版本|日志只写分数不写原始指标|日志无回滚点|状态新分数旧|为分数好看改判据
