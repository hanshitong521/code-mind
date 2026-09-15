# Evolution Log

> 追加式，一次 CHANGE→COMPARE 一条；旧条不删不改（改错则追加修正条）。
> 规格：`references/lifecycle.md` §5 ｜ 报告：`templates/skill-score-report.md`

## 索引

| # | 日期 | Skill | 版本 | 分类 | Verdict | 回滚点 |
|---|------|-------|------|------|---------|--------|
| 1 | | | → | KEEP/OPTIMIZE/MERGE/SPLIT/LAZY-LOAD/DISABLE-CANDIDATE/BLOCK | PASS/OPTIMIZE/BLOCK | |

---

## 记录模板（复制下面整块）

### <N> · <日期> · <skill_id>

版本:
日期:
触发原因:
分类结论:
操作人 / Agent:

#### 改动（一次一资源）

| 项 | 改前 | 改后 | 为什么 |
|---|---|---|---|
| description | | | |
| 根 SKILL.md 行数/字数 | | | |
| ref 路由 | | | |
| L2 移入/移出 | | | |
| 其他 | | | |

改动清单（逐条，含删除项）:
1.
2.

#### 评分前后

| 项 | 改前 | 改后 | Δ |
|---|---:|---:|---:|
| 总分 | | | |
| Grade | | | |
| TaskSuccess | | | |
| InputTokens | | | |
| OutputTokens | | | |
| ToolCalls | | | |
| DuplicateCalls | | | |
| Latency | | | |
| Rework | | | |
| EvidenceRetention | | | |

禁: 只写分数不写原始指标。

#### A/B 结果

| 固定项 | 值 |
|---|---|
| repo commit | |
| model / version | |
| task input | |
| acceptance criteria | |
| 环境 | |

重复次数:  A(前) / B(后) 对比结论一句:
覆盖任务: 小修改 [ ] Feature [ ] Debug [ ] 数据库 [ ] 跨模块 [ ] 测试修复 [ ] 高风险/大日志 [ ]
Hard Gate: 正确 [ ] 证据 [ ] 安全 [ ] 冲突 [ ] Trigger四类 [ ] 回滚 [ ] 真实A/B [ ]
Verdict: PASS | OPTIMIZE | BLOCK

#### 回滚点

| 项 | 值 |
|---|---|
| 改前路径 / git ref | |
| 回滚动作（一步可执行） | |
| 回滚后验证 | |
| 状态机变更 | 改前状态 → 改后状态 |

#### 后续

MONITOR 观察项 / 下次复审条件:

---

## 禁

禁: 自动删除 skill | 无回滚点记录 | 只写分数 | 无原始指标 | 一次记多资源 | 改旧条不追加修正 | 用「优化了 description」这类无判据描述 | 省略触发原因
