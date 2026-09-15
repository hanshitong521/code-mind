# 专项 Reviewer Prompt 片段（FOCUSED / COUNCIL 层使用）

派发方式与 reviewer.md 相同（Agent 工具、全新上下文）。**只取 risk 指定的专项节**追加在 reviewer.md 全文之后，并加一句：
"你只负责上述专项维度，其他维度略过；输出块格式与硬约束不变。"
专项发现与基础 Reviewer 的发现合并进 challenges.json，同样只是 CLAIM，一律过 Evidence Validator。

## V5 五专家委员会（COUNCIL 强制派发）

当 `risk.tier = COUNCIL`（总分 ≥ 15）时，**强制派发下面 5 个独立上下文 subagent**，每个按对应专项节 prompt 派发：

| # | 专项 | 适用场景 | 节 |
|---|---|---|---|
| 1 | concurrency | 抢单/秒杀/队列/重复消费/唯一约束覆盖 | 下文 `concurrency` 节 |
| 2 | data_integrity | 金额/库存/迁移/部分失败原子性/级联 | 下文 `data_integrity` 节 |
| 3 | security | 认证/越权/敏感数据落盘/注入 | 下文 `security` 节 |
| 4 | compatibility | 老客户端/老接口/灰度/字段语义变化 | 下文 `compatibility` 节 |
| 5 | testability | 验收可机械判定/外部依赖桩/异步可观测 | 下文 `testability` 节 |

派发顺序建议（参考 `state.mjs risk` 输出的 `top_dims` 排序）：
1. 风险分数最高的维度对应的专项先生成 CHALLENGE（最强攻击）
2. 剩余 4 个并发派发（每个 subagent 独立上下文，互不共享前序结论）
3. 全部 CLAIM 合并进 `challenges.json` 后再统一派 Evidence Validator

## security（security_risk 高分时启用）

目标：找出规格中被绕过、泄露或提权的路径。
检查：认证/鉴权缺口、未校验的外部输入、敏感数据进日志或落盘、注入面、会话与 token 语义、越权横向/纵向访问。

## data_integrity（data_impact / irreversibility 高分时启用）

目标：找出数据变错、变丢、变不回来的路径。
检查：迁移前后语义一致性、金额/库存精度与单位、部分失败时的原子性、孤儿数据、回滚后数据状态、删除级联。

## concurrency（concurrency_risk 高分时启用）

目标：找出并发交错下产生错误结果的执行序。
检查：检查-然后-行动竞态、唯一约束覆盖面、锁粒度与死锁、重试与幂等交互、定时任务与在线请求竞争、消息重复消费。

## compatibility（compatibility_risk 高分时启用）

目标：找出对存量调用方/客户端的破坏。
检查：响应字段增删与枚举扩容、参数校验收紧、错误码语义变化、Schema 变更对旧数据的含义、灰度期新旧并存。

## testability（evidence_gap 高分时启用）

目标：找出"写得出来但证明不了"的验收缺口。
检查：时间/随机依赖、外部依赖桩、异步结果可观测性、验收标准是否可机械判定、测试数据构造可行性。
