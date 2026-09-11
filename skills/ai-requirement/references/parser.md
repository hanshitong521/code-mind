# Requirement Parser 规则（Phase 2）

目标：把用户需求对照 facts.json 拆成四类，全部落盘。

## 四分类

| 类别 | 定义 | 落盘 |
|---|---|---|
| **KNOWN** | 能被 facts.json 佐证的部分 | 只在会话记录中陈述，不单独建文件 |
| **UNKNOWN** | 项目查不到的业务规则 | 生成 `questions.json` 条目 |
| **CONFLICT** | 需求与代码/文档现状矛盾 | `conflicts.json` |
| **ASSUMPTION** | 模型自己的推断 | `assumptions.json` |

## 判定纪律

- **R2 优先**：凡是"到期后自动退款""只能领一次""以服务器时间为准"这类业务规则，项目里查不到就进 UNKNOWN，禁止写进 KNOWN。
- 判断 KNOWN 必须给出对应的 FACT id；给不出的就不是 KNOWN。
- 需求与既有字段语义/接口行为/文档矛盾 → CONFLICT，severity=BLOCKING，左右两侧都要带证据（`path:line`）。
- 每条 ASSUMPTION 标注 `risk`：HIGH（写错会破坏数据/资金/权限）/ MEDIUM / LOW。**HIGH 风险 assumption 禁止进入最终开发规格**——要么转成 BLOCKING 问题问用户，要么取证升级为 KNOWN。

## Question 生成规则

从每条 UNKNOWN 生成 question：

```json
{
  "id": "Q-007",
  "topic": "expiration_boundary",
  "question": "红包到期与领取请求同时发生时，以哪个时间为准？",
  "reason": "影响并发判断与事务边界",
  "priority": "BLOCKING",
  "options": ["REQUEST_RECEIVED_AT", "TX_COMMIT_AT", "STRICT_EXPIRE"],
  "status": "OPEN"
}
```

`priority` 判定：

- **BLOCKING** — 不确认就可能写错业务：状态机、身份定义、金额计算、数据归属、权限、幂等、并发、删除语义、核心异常处理。
- **IMPORTANT** — 可以实现，但不同答案会改变体验或结构。攒着，BLOCKING 清零后再问。
- **OPTIONAL** — 不影响核心开发，直接采用明确默认值并在规格中标注，**不问**。

常见必查维度（对每个新需求过一遍）：新增字段还是复用？状态机怎么变？谁有权操作？并发下会怎样？重复请求怎么办？失败怎么回滚？对既有数据是否兼容？

## 重解析义务（R6）

Phase 3 每收到一个回答并冻结后，必须**全量重跑本阶段**：
- 新决策可能解开一批 UNKNOWN，也可能暴露新的 UNKNOWN（下一层问题）。
- 已 FROZEN 决策对应的问题置 status=ANSWERED，不删除、不重复问。
- 新产生的问题继续追加编号，不覆盖旧行。

重解析完成后更新 `session.json` 游标并快照到 `history/`。
