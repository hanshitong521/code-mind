# SkillMind 2.0.3 — 常驻成本治理 + MCP 成本审计

> 方法：`/ai-code` 流程 —— G0 判据 → G1 RED（最小失败测试）→ G2 GREEN → G4 对拍。
> 主题：**把「看不见的成本」变成「看得见的数字」**。2.0.2 补了 skill 侧的执行者，
> 本版补上「常驻来源可辨」与「MCP 工具 schema 成本可测」两块。
> 结果：常驻成本 **4075 → 573 tok/轮（−86%）**；selftest 19 → **24 项**；版本 2.0.2 → **2.0.3**。

## 0 一句话

一个 skill 白付了 **3502 tok/轮** 却没人发现——不是因为它超标，而是因为**没人知道它是常驻的**：
`load_mode` 只记录结果，不记录来源。本版让「故意常驻」与「忘了声明」可辨，并顺带把
MCP 工具 schema 的常驻成本纳入审计。

## 1 缺口清单（D11–D12）

### D11 `load_mode` 不记来源 → 「忘了声明」被当成「设计如此」

| 项 | 内容 |
|---|---|
| 现象 | `ai-requirement` 每轮付 **3502 tok**，审计只报「常驻且 2522 words > 200」，看不出这是**意外** |
| 根因 | `registry_build` 只在 `skill.yaml.loading.mode` 缺失时回落 `always`，**不记录「回落」这件事**。而全仓 6 个 skill 里只有 1 个有 `skill.yaml` → `always` 全是「没做决定」的默认值，不是设计选择 |
| 证据 | `ai-requirement` / `ai-concise` 既无 `skill.yaml` 也无 `disable-model-invocation` → `load_mode=always`；`ai-requirement` 实测 `est_tokens=3502` |
| 修复 | 新增 `load_mode_source ∈ {declared, default}`：`declared` = `skill.yaml.loading.mode` 或 frontmatter `disable-model-invocation` 显式指定；`default` = 两者皆无。审计据此分流 —— `default` 报 `LAZY-LOAD`（要求补声明），`declared` 报 `OPTIMIZE`（确认常驻是否必要） |
| 附带 | `ai-requirement` 补 `skill.yaml` → `on-demand`；`ai-concise` 补 `skill.yaml` → 显式 `always`（latch 型，本就该常驻） |

### D12 MCP 工具 schema 成本从未被度量 → `_audit_mcp` 实际是死代码

| 项 | 内容 |
|---|---|
| 现象 | 一个 40 工具、每轮全暴露的 MCP，与一个 3 工具的 MCP，在审计里长得**一模一样** |
| 根因 | `_mcp_entries` 只提取 `tools: <个数>`，从不估算 schema token。而**工具定义是每轮都进上下文的常驻成本**，与 always skill 的 `root_words` 同类 —— 同一类「成本存在但无人度量」的缺陷（对照 2.0.2 的 D8） |
| 证据 | `registry.json.mcps` 恒为 `[]`（无清单）；`_audit_mcp` 因此永远走「仓库无 MCP 清单」分支 → `--scope mcp` 实质不可用 |
| 修复 | `_tool_items()` 逐工具估算 `est_tokens(工具名 + description + 参数名/类型)`（显式 `schema_tokens` 优先）；server 级汇总 `tool_tokens` / `destructive` / `transport` / `owner`；`_audit_mcp` 重写为 5 条真判定（见 §3） |
| 新增资产 | `references/mcp-registry.md`（格式 + 成本口径 + 判定表）、`templates/mcp-registry.example.yaml` |

## 2 实测效果

### 2.1 常驻成本（每轮都付）

| skill | BEFORE | AFTER |
|---|---|---|
| `ai-requirement` | **3502** tok/轮（`always`，默认回落） | **0**（`on-demand`，显式声明） |
| `ai-concise` | 573 tok/轮（`always`，默认回落） | 573 tok/轮（`always`，**显式**声明） |
| **合计** | **4075 tok/轮** | **573 tok/轮（−86%）** |

### 2.2 `ai-requirement` 根文档瘦身（保留 `always` 也能省的部分）

| | 行数 | words | est_tokens |
|---|---|---|---|
| BEFORE | 196 | 2522 | 3502 |
| AFTER | 74 | 1290 | **1557**（−55.5%） |

移出内容 → `references/state-layout.md`（状态目录树）、`references/commands.md`（20+ 子命令）、
`references/gate.md`（V5 状态机 —— 此前**只存在于根文档**，是唯一会真丢的内容）。

**信息无损验证（逐项断言）**：R1–R12 全 12 条 ✓ · Phase 0–8 全 9 个 ✓ · 全部 18 个 reference 指针 ✓ ·
产物三层 ✓ · 铁律要点 ✓ · 下游栈 5 项 ✓ · 阶段细则约束 ✓ · STOP 行 ✓ —— 全部存活。

### 2.3 审计 findings（skill 范围）

| | BEFORE | AFTER |
|---|---|---|
| actionable | 8 | 15 |
| `ai-requirement` | `LAZY-LOAD`（常驻）+ `SPLIT` ×2 | 仅 `SPLIT` ×1（words 超 800） |
| `ai-concise` | `LAZY-LOAD`（误判为「未声明」） | `OPTIMIZE`（正确：已声明但超预算） |
| 消失 | — | **0**（既有 finding 未被吃掉） |

## 3 MCP 审计判定（新增能力）

| 条件 | action | 说明 |
|---|---|---|
| `standing: true` 且 `tool_tokens > 0` | `LAZY-LOAD` | 每轮都付；改按 phase 白名单暴露 |
| `tools > tool_budget.default_max_tools_per_phase`（默认 12） | `OPTIMIZE` | 超限须在 task bundle 显式声明理由 |
| 含任一 `destructive` 工具 | `OPTIMIZE` (risk=high) | 默认隐藏 + 二次权限检查 |
| 单工具 `tokens > MCP_TOOL_TOKENS_WARN`（600） | `OPTIMIZE` | description 疑似写进工作流 |
| 合计 `tool_tokens > MCP_TOKENS_WARN`（3000） | `OPTIMIZE` | 常驻成本超预算（≈12 工具 × 250 tok） |
| 以上都不命中 | `KEEP` | 合规 |

**实测**（用 `templates/mcp-registry.example.yaml`）：2 server 解析出 3 个工具、合计 ≈65 tok；
`filesystem` 因含 `destructive` 报 `OPTIMIZE`，`db-readonly` 判 `KEEP` —— 无误报。

## 4 验证证据

| 项 | 命令 | 结果 |
|---|---|---|
| 自测（裸 Python 3.9.6） | `selftest.py` | **22 PASS / 0 FAIL / 2 SKIP → OK**（共 24 项） |
| 仓级校验 | `scripts/validate_bundle.py` | `ok=true`，**0 errors**，2 warnings（既有） |
| 漂移 | `scripts/verify_skill_drift.py` | `PASS=2 DRIFT=2`；**`ai-skill-mcp-Y` 由 DRIFT 转 PASS** |
| 哈希语义一致 | `C.hash_tree` vs `_release_lib.hash_tree` | **逐字节一致**（无假 DRIFT） |
| 新增 skill.yaml | `manifest_validate` × 2 | 均 **0 error / 0 warning** |
| 新增断言 | `load_mode_source` / `mcp_tool_budget` | 2/2 PASS（G1 阶段先跑出 RED） |

**新增的 2 条 selftest 断言**：

- `load_mode_source` —— 合成 `default` 与 `declared` 两种来源，必须给出**不同** action；并检查注册表字段存在
- `mcp_tool_budget` —— 检查解析层产出 `tool_items`/`tool_tokens`/`destructive`；审计层对「常驻+超预算」报非 KEEP，
  对合规 server 判 KEEP（**防误报**）

## 5 未解决 / 需人工决策

| 项 | 现状 | 说明 |
|---|---|---|
| **上游未同步（重要）** | `ai-requirement` / `ai-concise` 是 `VENDORED_RELEASE_COPY`（`editable: false`），canonical 在 `hanshitong521/requirement-mind` / `concise-mind` | 本次改动需**同步回上游仓**，否则下次 re-vendor 会被覆盖。manifest 的 `content_hash` 我**故意未改**（它记录上游版本，改了会掩盖漂移） |
| `ai-design` / `ai-codeHealthMind` | 2 条既有 DRIFT；且 131/136 行、1774/1227 words 超预算 | 未动。修 DRIFT：`python3 scripts/build_release.py` |
| `ai-design` 模板重复 | `design-delivery.md` ↔ `output-spec.md` 各带一份技术设计文档模板，**已分化**（一个多「6. 本次变更面」节） | 已定位未修：应收敛为单一来源 |
| `ai-code` / `ai-design` / `ai-codeHealthMind` 缺 `skill.yaml` | 3 个 skill 无统一元数据 | 未动（本次只补了 `ai-requirement` / `ai-concise`） |
| `ai-skill-mcp-Y` L2 | 8/17 条 reference 超 2000 tok（`spec-v1` ≈5651） | 未拆：`spec-v1`/`spec-v2` 已被 `load:` 行 `禁默认整读` 挡住，属「深查才读」，拆了反而碎 |
| `ai-concise/reports/` | 40+ 个历史评分报告，多数近乎逐字节相同（**生成物**，非 references） | 未删（属生成物清理，需授权） |

## 6 本次**未做**的事（边界声明）

- **未动** `router.py` / `score.py` / `telemetry.py` / `manifest_validate.py` 的任何逻辑
- **未引入**任何第三方依赖（`python3 -S` 仍可跑）
- **未删**任何文件（无 `deleted:`；本次为纯增量 + 瘦身，非删减）
- **未自动修**任何被审计报出的 skill（报告与修复分离）
- **未创建** `shared/mcp-registry.yaml`（`shared/` 属其他 owner，见 `docs/ACCEPTANCE.md` §6 回滚边界）——
  只提供模板 `templates/mcp-registry.example.yaml` 与格式文档，由控制面 owner 决定是否落地

---

# 附录 A — 全仓扫尾（同日续做）

把 2.0.3 的主题（**让成本与来源可见**）推到全仓 6 个 skill。

## A1 补齐统一元数据：6/6 全有 `skill.yaml`

会话开始时全仓只有 1 个 skill 有 `skill.yaml`。现补齐：

| skill | load_mode | source | category | 行数 | root_words |
|---|---|---|---|---|---|
| `ai-code` | on-demand | declared | backend | 51 | 730 |
| `ai-codeHealthMind` | on-demand | declared | test | 53 | 697 |
| `ai-concise` | **always** | declared | docs | 58 | 448 |
| `ai-design` | on-demand | declared | docs | 59 | 1232 |
| `ai-requirement` | on-demand | declared | governance | 74 | 1290 |
| `ai-skill-mcp-Y` | on-demand | declared | governance | 61 | 692 |

6/6 过 `manifest_validate`（0 error / 0 warning）。**`load_mode_source` 全部为 `declared`** —— 不再有「忘了声明」。

## A2 根文档瘦身

| skill | 行数 BEFORE → AFTER | est_tokens BEFORE → AFTER |
|---|---|---|
| `ai-design` | 131 → **59** | 2016 → **1399** |
| `ai-codeHealthMind` | 136 → **53** | 1617 → **814** |

两者均从「超 120 行硬顶」回到合规。移出内容落到新建的 `references/toolchain.md`（ai-design）、
`references/{cli,workflow,rules,layout}.md`（ai-codeHealthMind）。**无损断言**：ai-design 43 项、
ai-codeHealthMind 66 项，全部 PASS（description 逐字一致 / 硬规则条数不减 / 指针无孤儿 / STOP 无丢失）。

## A3 `ai-design` 模板去重（真缺陷）

`references/design-delivery.md` 与 `references/output-spec.md` **各带一份技术设计文档模板，且已分化**
（一个多 `## 6. 本次变更面`、另一个多 `## 0. 节点证据` + 三个可选节）。同一工件两份权威模板 = 缺陷。

**收敛**：以 `output-spec.md` 为唯一模板权威；`design-delivery.md` 只留 D7 专属内容 + 指针；
`## 6. 本次变更面` 并入权威模板并标注 D7 专属，验收顺延为 `## 7. 验收` —— 两份编号就此对齐。
**顺带发现第三处分化**：`templates/design.md`（真正被拷贝的资产）也无 §6，已同步，消除三处不一致。

## A4 ⚠️ 一次自己造成的回归（已修，留作教训）

补 `skill.yaml` 时，`ai-design` / `ai-codeHealthMind` / `ai-requirement` 三处都把
**`查日志` / `对账` 抄进了 `triggers.exclude`** —— 而这两个词本来是 **`ai-skill-mcp-Y` 自己**的排除面。

后果：基准任务 **BM-06**（「定时**对账**任务偶发批次金额不平…」）让四个 skill 同时被硬排除
→ `recommended: []`，命中 `ACCEPTANCE.md` §5 Hard Gate「该用找不到（`recommended` 为空）」。

**修法**：排除词**只放本 skill 自己的易混邻域**，禁抄别家领域词。三处已回退。
**教训**：`exclude` 是**全局硬排除**，一个过宽的词会让整个注册表对该任务全部失效。

## A5 验证（最终）

| 项 | 结果 |
|---|---|
| 自测（裸 Python 3.9.6） | **22 PASS / 0 FAIL / 2 SKIP → OK**（24 项） |
| `validate_bundle` | `ok=true`，**0 errors**，2 warnings（既有，非本次） |
| **`verify_skill_drift`** | **`PASS=4, DRIFT=0`**（会话开始时 `PASS=1, DRIFT=3`） |
| 哈希语义 | `C.hash_tree` 与 `_release_lib.hash_tree` **逐字节一致**（4/4，无假 DRIFT） |
| 审计 actionable | 20 → **7**；「缺 skill.yaml」与「行超硬顶 120」两类 finding **全部消除** |

### 路由对拍（18 条基准任务，比成员集合）

| | 推荐一致数 |
|---|---|
| 基线（去掉全部新建 `skill.yaml`）vs 现状 | **18/18 完全一致** |

含 BM-06 回归的发现与修复在内，**最终零回归**。

## A6 仍未解决

| 项 | 说明 |
|---|---|
| **路由准确率 0.167（3/18）** | **既有问题，非本次引入** —— 基线同样 0.167。`ACCEPTANCE.md` §1.3 要求 >0.90，实测远不达标：多数任务 `matched=0`（相关性 < 0.12 阈值）或推荐了非期望 skill。这是**独立且严重**的既有缺陷，建议单独立项 |
| `root_words` 口径与中文 | 该口径按**单个中日韩字符**计数（`registry.md:41`），故中文根文档天然偏大：`ai-design` 59 行 = 1232 words。`>800 强制拆` 这条阈值对中文文档偏严，疑为英文语境设定，建议复核口径或对中文放宽 |
| `ai-requirement` / `ai-concise` 上游未同步 | 见正文 §5，需同步回 `hanshitong521/requirement-mind` / `concise-mind` |
| `ai-concise/reports/` | 40+ 个历史评分报告（生成物，多数近乎逐字节相同），未清理 |
| `deploy.bundle.yaml` | `ai-codeHealthMind` / `ai-skill-mcp-Y` 已声明但未进 bundle（`validate_bundle` 的 2 条既有 warning） |
| `ai-design/scripts/selftest.mjs` | `pathToFileURL is not defined` —— **改动前既有 bug**，未在本次范围

---

# 附录 B — 路由准确率根因定位（既有严重缺陷）

`docs/ACCEPTANCE.md` §1.3 要求 Router 准确率 **> 0.90**，实测 **0.167（3/18）**。
**本附录证明它不是本次改动引入的**（基线同样 0.167），并定位到根因、修掉其中一半。

## B1 根因一：CamelCase 标识符对项目类型推断不可见（**已修**）

`_hint_hit` 对 ASCII 提示按**词边界**匹配：

```python
re.search(r"(?<![a-z0-9_])mapper(?![a-z0-9_])", text)
```

这个设计本身是对的（防 `java` 命中 `javascript`）。但 `BrandMapper.xml` 归一化后是
一整块 `brandmapper.xml`，`mapper` 前面是字母 `d` → 词边界不成立 → `project_type=None`
→ `category` 权重（0.15）归零 → 总分跌破 `DEFAULT_MIN_CONFIDENCE`（0.12）→
**该任务「未命中任何技能」**。实测 18 条基准里 **7 条** `project_type=None`。

**修复**：新增 `hint_text()` —— 在 CamelCase 边界与 `_` 处插空格后再归一化
（`BrandMapper.xml` → `brand mapper.xml`）。只在**词边界**插空格、不改词内容，
故不引入跨域误命中（反例 `javascript 前端页面` 已由 selftest 锁定）。

| | BEFORE | AFTER |
|---|---|---|
| `project_type=None` | 7/18 | **5/18** |
| 路由准确率 | 0.167 | **0.222** |
| `routing_golden_cases` | 12/12 | **12/12（零回归）** |
| `router_expectations` | 3/3 | **3/3（零回归）** |

新增断言 `camelcase_hint`（G1 先跑出 RED，3 条 CamelCase 用例全失败）。

## B2 根因二：`ai-code` 的 L0 面是纯英文（**未修，需决策**）

18 条基准里 **12 条**期望 `ai-code`，但它几乎从不胜出：

- `description` 是**纯英文**（`Use when /ai-code: implement frozen docs/diagram/design.md…`）
- `triggers.include` 只有 `['/ai-code']`
- 派生 `tags` 也全是英文（`bug` / `dead` / `diff` / `frozen` / `implement` / `touched`…）

而基准任务是**中文**。中文二字滑窗与英文标签零交集 → `tag_score = 0`、`trigger_score = 0`，
只剩 `category`（0.15）与 `context`（≈0.05）。`project_type` 推不出或不是 `backend` 时，
总分必然 < 0.12 → 不匹配。

**实验（未落地）**：给 `ai-code` 的 tags 注入 24 个中文场景词（`改`/`修复`/`实现`/`重构`/
`报错`/`接口`/`参数`/`筛选`/`按钮`/`页面`/`组件`/`单测`/`分页`/`查询`/`列表`/`导出`/`权限`/
`日志`/`对账`/`业务`/`代码`/`联调`/`校验`/`字段`）：

| | 准确率 |
|---|---|
| 现状 | 0.222 |
| 加中文场景词后 | **0.667** |

**但有两处过触发**：BM-10、BM-16 从正确的 `ai-design` 被 `ai-code` 抢走。
「无脑加词」能大幅提分但伤 Precision，需要更精细的场景词设计。

**为什么没直接改**：`description` 是 Recall 关键字段，且 `ai-code` 声明了
`disable-model-invocation: true`（**本就不该由模型自动调用**，应由用户显式敲 `/ai-code`）。
「基准期望 `ai-code` 胜出」与「该 skill 声明为仅斜杠命令唤起」**本身存在矛盾**，
需人工判定是改 description、改 `disable-model-invocation`、还是修基准期望表。

## B3 仍未达标

准确率 **0.222**，距 **> 0.90** 仍有大差距。剩余差距主因是 B2（需决策），不是 B1（已修）。

> **注**：`benchmarks/tasks.yaml` **没有 `expect` 字段** —— 期望表只存在于
> `ACCEPTANCE.md` §1.3 的手写字典里，两者可能不同步。建议把期望标注进 `tasks.yaml`，
> 让「标注」与「任务」同源。
