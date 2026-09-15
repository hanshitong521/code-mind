# RequirementMind

WHAT 层：需求澄清、对抗审查、规格编译、Requirement Gate。

## 安装到业务仓（shejiuPro 等）

```powershell
cd E:\workA\A-skill\requirement-mind
node scripts/install.mjs E:\workA\shejiuPro
```

幂等覆盖 `.cursor/skills/requirement-mind/`；**不**动业务仓 `.requirementmind/` 会话数据。

## 门禁与迁移

```powershell
node scripts/peak-gate.mjs
node scripts/migrate-sessions.mjs --write <consumerRoot>
node scripts/selftest.mjs
```

栈合同：`../shared/pipeline-contract.yaml`（`requirement_mind` 为 peak_core）。
