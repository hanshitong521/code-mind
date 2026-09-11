# handoff · 契约→shared/handoff-schema.yaml validate_handoff.py
禁文件路径行号;引用@plan不贴全文;脱敏;建议下一步枚举{/ai-design,/ai-code,/ai-debug,无}
stated可写:用户原话|Explore所见|调用方字面量|用户选的方案
须标待确认:模型补全|UI翻camelCase|惯例推测|无字面量白名单
design→code必填:变更面 plan路径 范围 验收 验证档位 建议下一步 |选:假设 待代码确认 规则演进 接入门 identity_matrix verification_escalation
design→test必填:plan路径 只验SQL或含API 测试库写操作 建议下一步 |选:基址 夹具 接入门
code→test必填:变更面 plan引用 已跑验证 未跑验证 建议下一步 |选:改动文件 验证写库恢复 剩余风险 规则演进 接入门 identity_matrix
test→design必填:结论(SQL证伪|SQL证实Bug|全部PASS) 证据 建议 建议下一步 |选:数据恢复结果 接入门
分流:L1绿再升档;未跑验证=只补所列维
验证档位enum:micro-fix local-fix surface pr-ready release

## 示例（design_to_code · 校验用）

```yaml
# 设计 Handoff → 编码 / design_to_code
变更面: backend/api
plan路径: "@docs/plan/foo.plan.md"
范围: 模块X 表Y 接口Z
验收: 验收表 #1-#3 可独立测
验证档位: surface
建议下一步: /ai-code
```
