# SkillMind 2.0.2 — 审计执行者补齐报告

> 触发：外部设计文档《SkillMind Context OS V1.0》独立命中 3 处缺口，逐条核实后**全部为真**。
> 方法：`/ai-code` 流程 —— G0 钉判据 → G1 RED（最小失败测试）→ G2 GREEN → G4 对拍。
> 结果：补齐 3 类「**规范已写、执行者缺失**」的审计；selftest 19 → **22 项**；
> 审计 findings 8 → 20（新增 12、**消失 0**）；版本 2.0.1 → **2.0.2**。

## 0 一句话

V2.0.1 之前，尺寸治理**规范齐全但执行者缺失**：公式没实现、`root_words` 没人消费、
行数与 words 的单位被写反。本版把这三个执行者补上，**不新增规范、不改路由与评分**。

## 1 缺口清单（均有 Before/After 证据）

### D8 尺寸预算单位写反 → `root_words` 成为死字段

| 项 | 内容 |
|---|---|
| 现象 | `ai-requirement` 是 `always`（**每轮都付 token**）+ 196 行 / **2522 words**，审计一声不吭 |
| 根因 | `ROOT_LINES_HOT/WARN/SPLIT = 200/500/800` —— 把规范里 **words** 的 200/500/800 原值填进了 **行数** 常量。`root_words` 由 `registry_build.py:354` 算出并入库，**全仓无消费者** |
| 规范证据 | `token-loading.md:17/96`、`spec-v2.md:270`、`spec-v1.md:266-268`、`apply.md:20`、`templates/skill-skeleton/README.md:64`、`MIGRATION.md:153` 六处一致：根 `SKILL.md` **≤120 行**（硬顶）+ 常驻 **<200** / 普通 **<500** / **>800 强制拆**（words） |
| 修复 | 拆成两套常量：`ROOT_LINES_MAX=120`（行硬顶）+ `ROOT_WORDS_HOT/WARN/SPLIT=200/500/800`（words 分档）；`_audit_skill` 同时消费 `root_lines` 与 `root_words` |
| 附带 | 修 `references/registry.md:40` 那句自相矛盾的「`root_lines` … 尺寸治理依据（§8：常驻 <200 words）」（拿行数字段当词数依据） |
| 边界 | 两套判据**互不替代**：同一份根文档可能同时触发行数与 words 两条 finding（两个维度各超各的） |

### D9 `est_tokens` 公式未落地 → L2 无任何尺寸检查

| 项 | 内容 |
|---|---|
| 现象 | `references/spec-v1.md` ≈**5651 tok**、`spec-v2.md` ≈**5498 tok**，远超「单条 ≤2000 tokens」预算，审计不报 |
| 根因 | `token-loading.md:61` 写了公式 `est_tokens(s) = ceil(ascii/4) + ceil(cjk/1.5)`，但 `scripts/` **从未实现**（全仓 grep 无命中）；`_audit_skill` 只查 `refs` 断链，无尺寸检查 |
| 修复 | `_common.est_tokens()` 落地公式（**唯一实现**，零依赖，仅标准库）；新增 `_refs_over_budget()`；`_audit_skill` 加 L2 检查 —— 超 **2× 预算（4000）** 报 `SPLIT`，超 **1×（2000）** 报 `OPTIMIZE`（聚合为一条，带最重文件与超限条数） |
| 分级理由 | 17 条里 8 条超 2000。若全报 `SPLIT` 会诱导「拆到碎」，触发 `token-loading.md:33` 的「一次任务读 ≥5 个碎文件 = **失败**」。故只有 2× 以上才要求拆 |

### D10（本轮**未做**，边界声明）autoload 成本

外部文档建议把「默认自动加载面」计入成本（`Cost = root_words + autoload_words + dependency_words + …`）。

**方向是对的**：`ai-code` 的 `load:本页+references/lean.md` 那 3805 B 确实既不算 `root_lines` 也不算 L2，
是真实审计盲区。**但本仓不满足实现条件**：6 个 skill 里只有 3 个声明了 `load:`，
且 `ai-code` 那条**嵌在 `trig:` 行内**（`trig:/ai-code prio:rules>this load:本页+references/lean.md …`）、
3 种格式互不相同。硬解析会造出一个「近似死字段」——**正是 D8 要修的病**。
故本轮不实现，留待 `load:` 格式统一后再说。

## 2 验证证据

| 项 | 命令 | 结果 |
|---|---|---|
| 自测（PyYAML） | `selftest.py` | **22 PASS / 0 FAIL / 0 SKIP → OK** |
| 自测（裸 Python 3.9.6，无 PyYAML） | `/usr/bin/python3 selftest.py` | **20 PASS / 0 FAIL / 2 SKIP → OK** |
| 仓级校验 | `scripts/validate_bundle.py --json` | `ok=true`，**0 errors**，2 warnings（既有，非本次） |
| 哈希语义一致 | `C.hash_tree` vs `_release_lib.hash_tree` | **逐字节一致**（无假 DRIFT） |
| 路由金标 | `routing_golden_cases` | 12/12 PASS |
| 评分金标 | `scoring_golden_cases` | 8/8 PASS |
| 路由期望 | `router_expectations` | 3/3 PASS |
| 新增断言 | `est_tokens` / `size_budget_units` / `ref_token_budget` | 3/3 PASS |

**新增的 3 条 selftest 断言**（G1 阶段先跑出 RED，确认失败原因正确后才改实现）：

- `est_tokens` —— 口径锁定：`ceil(ascii/4)+ceil(cjk/1.5)`，含 6 组边界样本
- `size_budget_units` —— 常量单位正确（`ROOT_LINES_MAX=120`、`ROOT_WORDS_*=200/500/800`）
  + **合成反例**：`196 行 / 2522 words` 的 `always` 必须报 `LAZY-LOAD`；`60 行 / 180 words` 的合规常驻**不得**被误报
- `ref_token_budget` —— 拿真实文件 `references/spec-v1.md` 验证超预算能被报出

## 3 对拍（**比成员集合，不比全文**）

用 `git show HEAD:…/skillmind.py`（改动前的审计实现）跑同一份仓库，与改动后比 findings 成员集合：

| | BEFORE | AFTER |
|---|---|---|
| actionable | **8** | **20** |
| counts | `OPTIMIZE:8, KEEP:2` | `OPTIMIZE:11, SPLIT:7, LAZY-LOAD:2, KEEP:2` |
| 新增 | — | **12** |
| **消失** | — | **0** |
| 交集（未受影响） | — | 10 |

**消失 0 条 = 零回归**：没有任何既有 finding 被新逻辑吃掉。新增的 12 条全部可追溯到 D8/D9：

```
+ [OPTIMIZE]  ai-code            根 SKILL.md 730 words > 500：审视可否外移
+ [SPLIT]     ai-codeHealthMind  根 SKILL.md 136 行 > 硬顶 120：破坏渐进式披露
+ [SPLIT]     ai-codeHealthMind  根 SKILL.md 1227 words > 800：强制拆 references/
+ [LAZY-LOAD] ai-concise         常驻(always)且 448 words > 200：每轮都付 token
+ [SPLIT]     ai-design          根 SKILL.md 129 行 > 硬顶 120：破坏渐进式披露
+ [SPLIT]     ai-design          根 SKILL.md 1716 words > 800：强制拆 references/
+ [OPTIMIZE]  ai-design          L2 单条超预算 1/11 条（最重 references/render.md ≈2476 tok）
+ [SPLIT]     ai-requirement     根 SKILL.md 196 行 > 硬顶 120：破坏渐进式披露
+ [SPLIT]     ai-requirement     根 SKILL.md 2522 words > 800：强制拆 references/
+ [LAZY-LOAD] ai-requirement     常驻(always)且 2522 words > 200：每轮都付 token
+ [OPTIMIZE]  ai-skill-mcp-Y     根 SKILL.md 673 words > 500：审视可否外移
+ [SPLIT]     ai-skill-mcp-Y     L2 单条超预算：spec-v1.md ≈5651 tok > 4000；共 8/17 条超 2000
```

## 4 仍未解决（**未授权，未动**）

按 `SKILL.md` 的「默认最小：先报告后改」，以下**只报告不修**：

| 项 | 现状 | 建议动作 |
|---|---|---|
| `ai-requirement` | `always` + 196 行 / 2522 words / 21 refs —— 每轮都付的最大单项 | 拆 L0 摘要或改 `on-demand` |
| `ai-design` | 129 行 / 1716 words + `render.md` 2476 tok | 外移长文到 `references/` |
| `ai-codeHealthMind` | 136 行 / 1227 words | 同上 |
| `ai-concise` | `always` + 448 words（纯风格规则，可能本就该常驻） | 人工判断是否值得改 |
| `ai-skill-mcp-Y` 自身 | 673 words > 500 + L2 8/17 条超预算 | 拆 `spec-v1/v2` 或改由 `scripts/` 预处理 |
| 外部 DRIFT | `ai-design` / `ai-codeHealthMind` 记录过期（**非本次引入**） | `python3 scripts/build_release.py` |
| `deploy.bundle.yaml` | `ai-skill-mcp-Y` / `ai-codeHealthMind` 已声明但未进 bundle | 决定是否分发 |

## 5 净代码核算

| 文件 | 变化 |
|---|---|
| `scripts/_common.py` | +18（`_CJK_RE` + `est_tokens`） |
| `scripts/skillmind.py` | +67 / −10（常量拆分 + `_refs_over_budget` + 4 处新判定） |
| `scripts/selftest.py` | +3 断言（约 +120 行）+ 覆盖声明 19 → 22 |
| `references/registry.md` | 2 行改（`root_lines`/`root_words` 的判据与消费点写明） |
| `references/token-loading.md` | +4 行（公式实现点 + 机械消费点 + 三者互不替代） |
| `references/apply.md` | 尺寸段改写（修正「>800 行」→「>800 words」+ 行/词双判据 + 责任划分） |
| `VERSION` / `skill.yaml` / `SKILL.md` | 2.0.1 → 2.0.2 |

**无删除、无净增冗余**：新增全是「规范已要求、代码缺失」的执行者；未引入第三方依赖（仍可裸 `python3 -S` 跑）。

## 6 本次改动**不涉及**

- 未动 `router.py` / `score.py` / `telemetry.py` / `manifest_validate.py` 的任何逻辑
- 未改任何阈值语义（只是把单位修正回规范原意）
- 未自动修任何被报出的 skill（报告与修复分离）
- 未引入 embedding / Vector DB / 新目录结构（见外部文档 §12/§13 的评估：违反 `spec-v2.md:131` 的启用闸门
  「Recall < 0.8 **且** 注册表 > 30 条」，本仓仅 6 条；且会打破 `ACCEPTANCE.md:4.10` 的零依赖判据）
