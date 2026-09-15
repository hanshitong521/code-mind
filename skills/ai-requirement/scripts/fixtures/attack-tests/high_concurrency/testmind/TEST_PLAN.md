# TEST_PLAN（由 RequirementMind IR 自动生成）

- run_id: 2026-09-11T12:51:33.245Z
- source_session: 秒杀活动：1 万件商品 10 万 QPS 不超发
- total_cases: 1
- by_category: {"BUSINESS":1}

## 来源

- ir/acceptance.yaml (硬门槛 + BLOCKING/IMPORTANT 验收)
- ir/business-rule.yaml (FROZEN 业务规则)
- ir/decision.json (决策追溯)
- facts.json (项目事实，作为 case source 引用)

## 用途

test-mind 可直接读 testmind/TEST_CASES.yaml 跑 run_pipeline；
未填 expected.http 的 case (BUSINESS/BOUNDARY/ACCEPTANCE) 由 test-mind 标记为 NOT_TESTED（不阻塞 final_gate）。

## Case 总览

- `P0-HAPPY` [BUSINESS/P0] source=FACT-402 — 主路径烟测（来自 FACT-402：POST /api/seckill/{sku_id}/buy 已有）
