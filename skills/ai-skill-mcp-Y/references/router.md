# SkillMind Router — 运行时唯一权威路由

> 规格：`spec-v2.md` §3.2 / §9 / §14.1 / §14.3 ｜ 实现：`scripts/router.py`
> 一句话：**读注册表 → 硬过滤 → 打分 → 装链 → 输出可解释推荐**。只做「选」，不做「做」。

## 0. 唯一权威（§9.4）

Brain / TokenMind / SkillMind / MCP **不得各做一套 Router**。运行时权威只有本脚本：

| 层 | 只提供什么 | 不得做什么 |
|---|---|---|
| RequirementMind | 项目类型 / 复杂度 / 风险（来自 FROZEN 决策） | 自己选技能 |
| project-brain | 历史 WHY、ADR | 自己选技能 |
| TokenMind | 预算、`estimated_tokens` | 自己选技能 |
| MCP Gateway | 工具清单、身份 | 自己选技能 |
| **SkillMind Router** | **唯一的推荐 + 执行链 + 排除理由** | 写业务码、改生产配置 |

`--project-type` / `--risk` / `--complexity` 是**输入信号**，不是决策。缺省时 Router 自行推断并在 `inputs.project_type_source=inferred` 里标注。

## 1. 输入

| 来源 | 内容 |
|---|---|
| CLI | `--task`（必填）、`--project-type`、`--risk`、`--complexity`、`--top`、`--min-confidence`、`--method`、`--registry`、`--root`、`--confirm-risk`、`--json` |
| 注册表 | `<root>/.skillmind/registry.json`（结构见 spec §14.2，由 `registry_build.py` 生成） |
| 控制面 | `shared/capability-registry.yaml` 的 `capabilities` / `phases`（只读） |
| 历史 | `<root>/.skillmind/scores.json` 的最新分（注册表 `score` 为 null 时的补位，只读不写回） |

契约见 `schemas/route-request.schema.json`。

**注册表缺失时的自愈**：`--registry` 指向的文件不存在 → `import registry_build` 调 `build_registry(root)` 重建并落盘 → 仍失败则提示先跑
`python3 scripts/registry_build.py --root <R>`，退出码 `2`。Router **不自己实现注册表扫描**（那是 registry_build 的职责，重复实现必然产生假 DRIFT）。

## 2. 输出（§14.3）

```json
{
  "schema_name": "skillmind-route-result", "schema_version": 1,
  "task": "...", "method": "rule+tag", "confidence": 0.9,
  "recommended": [{"skill_id": "ai-code", "confidence": 0.29,
                   "reasons": ["category:backend", "history:95.8", "context:root_lines=51"],
                   "category": "backend", "status": "verified",
                   "breakdown": {"tag": 0.0, "trigger": 0.0, "category": 1.0,
                                 "history": 0.96, "context": 0.87}}],
  "chain": [{"order": 1, "phase": "coding", "skill_id": "ai-code",
             "why": "capability code.implement → ai-code"}],
  "excluded": [{"skill_id": "x", "reason": "status=blocked：安全/合规一票否决，永不推荐"}],
  "warnings": [],
  "inputs": {"project_type": "backend", "project_type_source": "inferred"}
}
```

契约见 `schemas/route-result.schema.json`。`inputs` 是 V2 扩展字段（复现与审计用），不参与打分。

**reasons 必须可解释**，标签即证据：

| 前缀 | 含义 |
|---|---|
| `tag:X` | 命中注册表 `tags` 里的整词 X |
| `keyword:X` | 命中 description 正向从句里的关键词 X（中文按 bigram 还原成词） |
| `trigger:X` | 命中 `triggers.include` 里的 X |
| `category:X` | 技能 category 与任务项目类型一致 |
| `history:N` | 历史评分 N（无记录为 `history:none`） |
| `context:root_lines=N` | 上下文成本依据 |
| `status:deprecated` / `downgraded:risk=high@critical` | 硬过滤副作用标注 |

## 3. 硬过滤（§9.2，**先于打分**）

| 规则 | 处理 |
|---|---|
| `status == blocked` | 进 `excluded`，**永不推荐**（只能人工解除） |
| `triggers.exclude` 命中任务原文 | 进 `excluded`，理由记 `exclude 命中：<词>` |
| `status == deprecated` 且有替代 | 进 `excluded`，理由记 `已有替代 <id>` |
| `status == deprecated` 且无替代 | **仍推荐**，reasons 追加 `status:deprecated（无替代，仅标注推荐）` + warning |
| `--risk critical` 且技能 `risk == high` | 降级为候选，reasons 追加 `downgraded:...` + warning；`--confirm-risk` 可解除 |

`exclude` 命中判定（`router.exclude_hit`）：

| 形态 | 判据 |
|---|---|
| 单 token / 中文短语 | 整句**子串**命中 |
| 多词英文短语（`requirement freeze`） | 所有内容词（≥4 字母）**全部出现**（AND 语义）——整句子串匹配对短语过严：任务写成 `freeze requirement` 就漏判，等于护栏失效 |

`exclude` 由 `_common.derive_excludes()` 从 description 的**否定从句**派生（`Not for …` 之后的部分），并与 `skill.yaml: triggers.exclude` 合并。否定从句不派生 = 精确度无护栏。

替代判定：同 `category` 且至少 1 个标签交集、且对方非 `blocked`。

**否定从句**：description 里 `Not for …` / `不适用` / `禁止用于` 之后的内容不进关键词面，落在其中的触发词（如 ai-skill-mcp-Y 的 `查日志`、`/ai-code`）直接剔除。这是防跨域误触发的第一道闸。

## 4. 打分（§9.1）

```
route_score(skill, task) =
    0.45 × 标签/关键词命中
  + 0.25 × 触发词命中（triggers.include）
  + 0.15 × 项目类型匹配（category）
  + 0.10 × 历史成功率（score / 100）
  + 0.05 × 上下文成本惩罚      ← 1 - clamp01(root_lines / 400)
```

| 分项 | 归一规则 | 饱和点 |
|---|---|---|
| 标签/关键词 | 命中数 / 2 | 命中 ≥2 个即满分 1.0 |
| 触发词 | 任一命中即 1.0 | 单条命中即饱和 |
| 项目类型 | category == project_type 记 1.0，否则 0 | — |
| 历史成功率 | `clamp01(score/100)`；无记录记 0 | — |
| 上下文成本 | `1 - clamp01(root_lines/400)`，越大越扣 | 400 行扣满 |

**分词**：ASCII 按整词（`[a-z][a-z0-9_.-]*`），中文按二字滑窗。整词取词是关键——`java/sql` 这类复合标签不会被拆成 `sql` 而误命中 SQL 任务；中文 bigram 让「审计MCP」这类混排触发词能按子串命中，并在 reasons 里还原成「澄清需求」这样的完整词。

**触发词命中**（防二字子串误触发）：
1. 规范化后整条触发词是任务原文子串 → 命中；
2. 否则分词后：单 token 触发词需该 token 命中；多 token 触发词需 **≥2 个 token 命中且覆盖 ≥50%**。

第 2 条挡住「需求已冻结」被 `澄清需求` 里的 `需求` 误触发这类情况。

**入选条件**（两条同时满足）：
- `route_score ≥ --min-confidence`（默认 0.12）；
- **至少一条相关性信号**（tag/keyword、trigger、category 任一 > 0）。

只靠 `history` + `context` 这类「质量分」进榜 = 无依据推荐，一律剔除。全部不满足时 `recommended = []` 并给 warning——**宁可说没有，也不硬凑**。

**同量级带（列表级，`RELATIVE_BAND = 0.45`）**：过阈值的项还要满足 `route_score ≥ 首选 × 0.45`，否则降为 `excluded` 并写明理由。这条专治两类弱信号噪声：

| 噪声源 | 实测 | 为什么是噪声 |
|---|---|---|
| 纯 `category` 命中 | 治理任务里 `ai-requirement` 只靠 `category=governance` 拿 0.18 | 同 category ≠ 同职责，零标签/触发词命中 |
| 单个中文二字窗口 | `ai-design` 靠 description 里的「审计」二字拿 0.25 | 通用词偶然命中，不是相关性 |

取值依据：真正需要多技能协同的任务比值约 0.84（如 requirement 0.73 + coding 0.61），远高于 0.45；被挡掉的都是比值 < 0.45 的噪声项。`tests/routing-cases.json` 的 RT-02 / RT-03 / RT-09 就是这三个红线的回归锚点。

## 5. 链装配（§9.3）

顺序即执行顺序：`requirement → design → coding → verification`。

```
阶段来源（禁硬编码具体 skill 名）：
  1. 注册表 category → phase     （主口径）
     backend/frontend/data/infra → coding ｜ docs → design ｜ test → verification ｜ governance → verification
  2. capability-registry         （补位：该阶段完全没有 category 映射时，如 requirement）
     capability.skill 优先；无 skill 字段才用 capability.owner 回落到同名注册技能
     （requirement.clarify.owner=requirement-mind → name 匹配 → ai-requirement）
```

- 链成员**只能来自已过阈值的推荐**；阶段候选按 route_score 取最高。
- `governance` 类技能只在 `project_type == governance` 时充当 verification 收敛角色，不为普通工程任务当验证步骤。
- 任务阶段由关键词信号推断；`已冻结/已确认/已定稿` 命中时该阶段视为已完成，不再进链。`coding`/`design` 在场时追加 `verification`；无候选则该段缺失并告警（指明 capability-registry 里对应的 owner）。
- 未识别任何工程阶段（如纯风格类 overlay 任务）→ `chain = []` + warning，**不硬装链**。

## 6. 四级演进（§3.2，同一时刻只启用一级）

| 级 | 方法 | 启用条件 | 现状 |
|---|---|---|---|
| 1 | 规则 + 标签 | 默认，零依赖 | **已实现**，`method=rule+tag` |
| 2 | Embedding 相似度 | 规则召回 < 0.8 且注册表 > 30 条 | 未实现 |
| 3 | LLM Router | 多义/跨域任务占比 > 20% | 未实现 |
| 4 | 多专家评分 | 高风险 / 关键路径 | 未实现 |

`--method embedding|llm` 会照常接受，但输出 `method=rule+tag` 并在 `warnings` 里说明该级未实现、已回落第 1 级。**禁静默假装跑过**。

## 7. 命令

```bash
# 人类可读（默认）
python3 scripts/router.py --task "改一个 MyBatis SQL"

# 机器可读
python3 scripts/router.py --task "审计一下 skill 的触发器" --json

# 显式信号 + 条数
python3 scripts/router.py --task "..." --project-type backend --risk critical \
        --complexity L2 --top 3 --min-confidence 0.2

# 指定注册表 / 仓根
python3 scripts/router.py --task "..." --registry .skillmind/registry.json --root .

# 统一入口
python3 scripts/skillmind.py route --task "..." [--json]
```

退出码：`0` 路由完成（含「无命中」）；`1` 路由执行失败；`2` 用法或环境错误（缺注册表、空 task、非法参数）。

## 8. 反模式（违反即 FAIL）

| 反模式 | 为什么错 |
|---|---|
| 硬编码 skill 名进链 | 注册表一变链就错；必须由 category/phase 推导 |
| 先打分后过滤 | `blocked` 技能会先污染排序，§9.2 明确硬过滤先行 |
| 推荐不带 reasons | 无法审计、无法复现、Agent 无法复核 |
| 只按 history 排名 | 高分但不对口的技能会顶掉正确技能 |
| 把 `Not for` 从句当正向关键词 | 跨域误触发的头号来源（如 `Java/SQL` 命中 SQL 任务） |
| 无命中时硬凑一个推荐 | 假阳性比「没有」更贵；必须空 + 告警 |
| 多层各做一套 Router | 冲突 + 重复决策（§9.4） |
| Router 里写业务码 / 改生产配置 | 越界：SkillMind 只做「选」 |
| 声称跑过未实现的 embedding/LLM 级 | 静默降级即造假；必须告警 |
| 自己实现注册表扫描 / 哈希 | 与 `registry_build`、`_release_lib` 语义漂移 → 假 DRIFT |
| 引入第三方依赖或 3.10+ 语法 | 破坏「裸 Python 3.9 可跑」硬约束 |

## 9. 验收锚点

`tests/routing-cases.json` 的 12 条金标用例（`positive` / `negative` / `boundary` / `conflict`）：

- `expect_top`：必须排在推荐首位；
- `expect_not`：不得排在首位；当 `expect_top` 为 `null` 时收紧为「不得出现在 recommended 中」；
- 每条推荐必须有非空 `reasons`，链成员必须能在注册表里找到。

三条核心断言：改 SQL → `ai-code`；审计 skill/MCP → `ai-skill-mcp-Y`；澄清需求并冻结 → `ai-requirement`。
