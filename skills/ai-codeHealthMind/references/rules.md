# 配置与抽象判据

> 根文档 `SKILL.md` 的 `ref:` 路由表命中「`.codehealth.yml` 旋钮 / accepted_risks / 错误抽象 7 问」时读本页。

## 1 配置文件

`.codehealth.yml`（`codehealth init` 生成；模板见 `.codehealth.example.yml`）。
严格校验：未知 key / 类型错误 → 硬失败，不静默取默认值。

## 2 关键旋钮

- `tools.*.enabled` — 关掉某个 provider
- `tools.<t>.home` / `.bin` — 或环境变量 `CHM_PMD_HOME` / `CHM_SPOTBUGS_HOME` / `CHM_SEMGREP_BIN` / `CHM_KNIP_BIN` / `CHM_JAVA_HOME`
- `review.backend` — `off` \| `rule`（确定性本地启发式，报告中如实标注）\| `llm`（`llm_command` 必须配置，否则报 CONFIG 错误，**不偷偷降级**）
- `gates.*` — 阻断阈值（`max_new_medium` 等）
- `dead_code.allow_auto_delete` — 默认 `false`；即使为 `true`，也只改「未用 import / debug 残留」这类可证机械项
- `accepted_risks` — 带 `expires`，**过期即重新阻断**

## 3 错误抽象 > 重复：7 问

出现重复**不得自动抽象**。要求抽象前必须逐条回答：

1. 同语义？
2. 同变化原因？
3. 同生命周期？
4. 已有模式？
5. ≥3 次？
6. 降低成本？
7. 引入更多泛型？

任一答不上 → 保持重复，不引入抽象。
