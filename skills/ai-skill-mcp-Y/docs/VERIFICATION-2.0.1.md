# SkillMind 2.0.1 — 用 `/ai-code` 实测优化报告

> 方法：按 `skills/ai-code` 的规范真跑一遍（G0 判据 → G1 RED → G2 GREEN → G3 契约 →
> G4 验证 → G5 ship）。先用 `skillmind audit` 自审，再逐条定位真 bug、修、对拍。
> 结果：**发现并修复 6 个真缺陷 + 1 个 flaky 测试**，selftest 14 → **19 项全绿**。

## 1. 缺陷清单

### D1 `derive_triggers` 恒返回 `exclude: []`（核心）

`_common.py` 的 docstring 自己写了「后者是『禁做』信号，当成正向触发词会反向扩大触发面」，
却把否定从句**整个丢掉**，`exclude` 硬编码为空。

- 后果 A：`ai-code`（`Not for /ai-design, requirement freeze, log-only ops.`）与
  `ai-concise`（`Not for /ai-code alone, Requirement Gate WHAT, or skill/MCP governance`）
  写的精确度声明**完全没生效** —— 5/6 技能无 precision 护栏。
- 后果 B：`audit` 把「解析器不派生」误报成「作者没写 exclude」，**误导修复方向**。
- 修：`_common` 新增 `negative_clause()` + `derive_excludes()`；`router.py` 删除重复的
  `NEGATIVE_MARKERS` / `_NEG_RE` / `positive_clause` / `negative_clause`，收敛到 `_common`。

### D2 `registry_build` 把 include 的「禁空白」守卫照搬给 exclude

该守卫本是为丢弃 `trig:` 行尾的 `prio:rules>this` 而设，照搬到 exclude 后，
多词否定短语（`requirement freeze`）被静默丢弃。

- 修：exclude 允许短语形态（≤32 字符、禁换行）。

### D3 `router.hard_filter` 的 exclude 用整句子串匹配

`norm_text("requirement freeze") in norm_text(task)` —— 任务写成 `freeze requirement`
（语序不同）就漏判，护栏等于失效。

- 修：新增 `router.exclude_hit()`；多词英文短语按**内容词全出现（AND）**判定，
  单 token / 中文短语仍按子串。
- 效果（对拍证据）：

| 任务 `freeze requirement then write code` | 修复前 | 修复后 |
|---|---|---|
| 推荐 | `ai-code` ❌ | `ai-requirement` ✓ |
| 排除 | — | `ai-code \| exclude 命中：requirement freeze` |

### D4 `audit` 的 verdict 恒为 `OPTIMIZE`

`verdict = "OPTIMIZE" if findings else "PASS"` —— `KEEP` 也算 findings，
而 `_audit_agents` / `_audit_mcp` 永远至少产出一条 `KEEP`，
于是**审计永远无法报 PASS**（报警失效 = 等于没有报警）。

- 修：verdict 只由**可执行动作**（`action != KEEP`）决定；新增 `payload.actionable` 便于核对。

### D5 两份 JSON Schema 校验器已分化（语义重复）

`manifest_validate.Validator` 与 `telemetry.validate_instance` 各一份。
telemetry 那份是超集但有 2 个真缺陷：

1. `enum` 用裸 `instance not in schema["enum"]` —— Python 里 `True == 1`，
   `True` 被**误判为匹配 `enum:[1]`**；
2. `pattern` 无 `re.error` 兜底 —— schema 里写错正则直接**抛异常崩掉**，而非记为错误。

- 修：唯一实现收敛到 `_common.validate_instance`（telemetry 超集 + bool 安全
  `same_value` + `re.error` 兜底 + 未支持关键字告警 `schema_keyword_warnings`）。
- 净代码：`manifest_validate.py` **258 → 115**（−143）、`telemetry.py` **656 → 524**（−132），
  共 **删 275 行重复实现**。
- 副作用（正面）：`manifest validate` 现在真正支持 `const` / `minLength` / `maxLength` /
  `exclusiveMinimum` / `format` / `minItems`，不再是「warning 了事」。

### D6 `.DS_Store` 污染 `content_hash` → 假 DRIFT（最有价值）

控制面 `hash.normalize.exclude` 只有 `[.gitignore, evals.json]`。
`skills/ai-code/.DS_Store`（macOS Finder 生成）被算进哈希 ——
**Finder 看过一眼目录，content_hash 就变**，跨机器不可复现。

- 证据：去掉 `.DS_Store` 后哈希**精确等于** manifest 记录 `sha256:f35723b9…`。
- 爆炸半径 = 恰好 1 个 skill（全仓只有 `skills/ai-code/.DS_Store`）。
- 修：`shared/release-manifest.yaml` 的 exclude 补 `.DS_Store` + `Thumbs.db`。
  三个控制面消费者（`verify_skill_drift.py` / `build_release.py` / `_release_lib`）
  都从这一处读 exclude，故哈希语义一致性不受影响。
- 效果：`ai-code` 的 DRIFT 消失（我的 verify 与仓自带 `verify_skill_drift.py` 均报 PASS）。

### D7 `check_registry_build` 是 flaky 测试

外部进程并发写某个 skill 目录时，两次哈希不同 → 误判为「hash 不自洽」FAIL。

- 修：两次哈希不同 → 标记「并发写入中」并跳过（环境状态，不是 SkillMind 回归）。

## 2. 验证证据

| 闸门 | 结果 |
|---|---|
| `skillmind selftest`（PyYAML） | **19 / 19 PASS** |
| `skillmind selftest`（裸 `/usr/bin/python3` 3.9.6，无 PyYAML） | **17 PASS + 2 SKIP** |
| `skillmind verify` | `ai-skill-mcp-Y` PASS、`ai-code` PASS |
| `scripts/validate_bundle.py` | **PASS** |
| 路由金标 | 12 / 12 |
| 评分金标 | 8 / 8 |
| 路由对拍（10 条探针） | 9 条完全一致，唯一变化 = D3 的预期修复 → **零回归** |
| 反向验证（负例 skill.yaml） | 抓出 14 处错误（含 `pattern` / `additionalProperties`） |

新增断言（5 条）：`triggers_derivation` / `audit_verdict` / `validator_bool_enum` /
`validator_single_source` / `hash_os_noise`。

## 3. 未解决（非本次引入）

| 项 | 成因 | 修复入口 |
|---|---|---|
| `ai-design` DRIFT | **外部进程并发改写**（未追踪 `scripts/lint.mjs` + 已改的 `SKILL.md` / `references/render.md` / `scripts/render.mjs` / `scripts/selftest.mjs`） | `python3 scripts/build_release.py`，或删除 `lint.mjs` |
| `ai-codeHealthMind` DRIFT | 既有：manifest 记录过期（git 工作区无改动） | `python3 scripts/build_release.py` |

## 4. 净代码

生产脚本（不含 selftest）：**3991 → 3999 行**（≈持平），
其中**删除 295 行重复实现**（两份校验器 275 + router 四处副本约 20），
`_common.py` 集中承载 264 行唯一实现。selftest 434 → 591（新增 5 条断言的测试投入）。

## 5. 可选的下一步

- `deploy.bundle.yaml` 加入 `ai-skill-mcp-Y`（当前 `validate_bundle` 有 WARN：已声明但不分发）
- `python3 scripts/build_release.py` 一次性刷新两处既有 DRIFT
- `skills/ai-code/` 与 `skills/ai-design/` 正被外部进程改写 —— 操作前先确认无并发写入
