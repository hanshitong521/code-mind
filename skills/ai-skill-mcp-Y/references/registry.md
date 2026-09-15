# Registry（注册表规范）

> SkillMind V2.0 §3.1 / §11 / §14.2 的落地说明。生成物 = `<repo>/.skillmind/registry.json`，
> 由 `scripts/registry_build.py` 机械生成，是路由 / 评分 / 验证 / 进化的**唯一输入真源**。
> 契约文件 = `schemas/registry.schema.json`（draft-07）。禁: 手改 registry.json。

---

## 1. 定位与边界

| 项 | 内容 |
|---|---|
| 是什么 | skill 身份 + 标签 + 状态 + 成本 + 风险 + 控制面归属的**机械快照** |
| 不是什么 | 不是路由结果（那是 `route-result.json`）；不是评分记录（那是 `scores.json`）；不是 skill 文件管理器 |
| 生成时机 | 每次 skill 增删改、控制面变更、发布前；离线或准实时 |
| 落位 | `<repo>/.skillmind/registry.json`（不进任何 `artifact_path`，故**不影响 content_hash**，不产生假 DRIFT） |
| 消费方 | Router（候选集与硬过滤）、Score Engine（skill_id 对齐）、verify（bundled/hash 一致性）、SkillMind CLI |

---

## 2. 数据结构（每条 skill 22 字段）

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `skill_id` | string | skill 目录名 | 稳定 id，**禁改**；改名 = 断链 |
| `name` | string | frontmatter.name > skill.yaml.name > 目录名 | 展示名可与 id 不同（`ai-design` → `DiagramMind`） |
| `path` | string | 固定 `skills/<id>/SKILL.md` | 相对仓根，posix 分隔 |
| `dir` | string | `skills/<id>` | 相对仓根 |
| `description` | string | frontmatter.description | 压成单行；只回答「何时用 / 何时不用」 |
| `category` | enum(7) | 推断表 / frontmatter / skill.yaml | 路由打分要素 |
| `tags` | string[] | `derive_tags` ∪ skill.yaml.tags | 小写、去重、排序 |
| `version` | string\|null | frontmatter > skill.yaml > release-manifest | 三处皆无 → `null`（禁臆造 `0.0.0`） |
| `status` | enum(5) | 状态机（§3） | `draft/testing/verified/deprecated/blocked` |
| `score` | number\|null | `.skillmind/scores.json` | 无记录 → `null`（禁默认 100） |
| `owner` | string\|null | capability-registry > release-manifest.source_repo > skill.yaml | 能力归属 |
| `load_mode` | enum(3) | skill.yaml.loading.mode > `disable-model-invocation` | `always/on-demand/deep` |
| `risk` | enum(4) | frontmatter/skill.yaml | 默认 `low` |
| `destructive` | bool | frontmatter/skill.yaml | 默认 `false` |
| `always_apply` | bool | 派生 `load_mode == "always"` | 常驻 L0 者 |
| `root_lines` | int | `SKILL.md` 行数 | 尺寸治理依据（§8：常驻 <200 words） |
| `root_words` | int | 拉丁词 + 单个中日韩字符 | 中文无空格，故按字计；口径与 `wc -w` **不同** |
| `refs` | string[] | `references/**` 递归 | 相对 **skill 目录**（如 `references/lean.md`） |
| `triggers` | {include,exclude} | `derive_triggers` ∪ skill.yaml.triggers | **include** 必须无空白单 token（丢 `trig:` 行尾的 prio 说明）；**exclude** 允许短语（`requirement freeze`），源自 description 否定从句 + skill.yaml |
| `bundled` | bool | release-manifest ∪ deploy.bundle | 是否进分发 |
| `hash` | string | `hash_tree(dir, manifest_exclude())` | `sha256:...`，与控制面逐字节等价 |
| `source` | enum(2) | `release-manifest` / `filesystem` | 有 manifest 记录即前者 |

顶层字段：`schema_name`、`schema_version`、`generated_at`、`root`、`sources`、`skills`、`rules`、`mcps`、`overlap`、`stats`。

---

## 3. 状态机与 blocked 一票否决

```
draft ──▶ testing ──▶ verified ──▶ deprecated
  │          │            │            │
  └──────────┴────────────┴────────────┴──▶ blocked（安全/合规一票否决）
```

| 状态 | 进入条件（本仓机械判定） | 路由行为 |
|---|---|---|
| `testing` | 默认值（无 release-manifest 记录） | 可推荐，标注未验证 |
| `verified` | 有 release-manifest 记录 **且** `bundled == true` | 正常推荐 |
| `draft` | 人工裁决 | 仅显式点名 |
| `deprecated` | 人工裁决 | 仅无替代时推荐，且标注 |
| `blocked` | 人工裁决（`status-overrides.json`） | **永不推荐**，硬过滤第一优先级 |

人工裁决来源：`<repo>/.skillmind/status-overrides.json`，形如 `{"ai-x": "blocked"}`。
`blocked` 覆盖一切自动判定，**只能人工解除**；系统可自动产出 `DISABLE-CANDIDATE`，但**禁自动删除** skill。

---

## 4. 扫描规则

| 目标 | 路径 | 规则 |
|---|---|---|
| skill 根 | `<root>/skills/*/SKILL.md` | **只扫一层**；无 SKILL.md 的目录不入表 |
| frontmatter | 同上 | 取 `name/description/version/disable-model-invocation`；解析失败不中断，回落到 skill.yaml |
| skill.yaml | `<root>/skills/<id>/skill.yaml` | 可选；提供 version/category/loading/risk/tags/triggers 的显式声明 |
| refs | `<root>/skills/<id>/references/**` | 递归；跳过 `.git/__pycache__/node_modules/.codehealth/reports` |
| 常驻规则 | `<root>/.cursor/rules/**/*.mdc` | **只收 `alwaysApply: true`**；记 path/lines |
| MCP | `shared/mcp-registry.yaml`、`shared/mcp-manifest.yaml`、`.skillmind/mcps.{yaml,json}` | 四处皆无 → `mcps: []`（**禁臆造**） |
| hash | 整个 skill 目录 | `_common.hash_tree` + `manifest_exclude()`；**禁自实现哈希** |

`--root` 可指向任意仓（含被治理的项目仓）；默认 `_common.repo_root()`。

---

## 5. 与控制面映射表（只读消费，禁反向改写）

| 控制面 | 读取字段 | 写入注册表 |
|---|---|---|
| `shared/release-manifest.yaml` | `skills[<id>]` 存在 | `bundled=true`、`source="release-manifest"` |
| 同上 | `version` | `version`（frontmatter 缺省时） |
| 同上 | `content_hash` | **不直接写入**；与 `hash_tree` 结果比对（不等 = DRIFT，由 verify 判） |
| 同上 | `source_repo` | `owner`（capability-registry 未命中时） |
| `shared/capability-registry.yaml` | `capabilities[].skill == skill_id` → `owner` | `owner` |
| `deploy.bundle.yaml` | `skills[]` 命中 | `bundled=true` |
| `shared/schema-versions.yaml` | 契约版本 | 仅登记于 `sources`，用于版本兼容判定 |

`hash` 的语义**必须**与 `scripts/_release_lib.py` 一致（CRLF→LF、行尾 rstrip、同一忽略目录集），
否则「SkillMind 一个哈希、release-manifest 另一个哈希」→ 假 DRIFT。

---

## 6. 字段推断链（缺省时）

| 字段 | 优先级链 | 兜底 |
|---|---|---|
| `category` | frontmatter > skill.yaml > 目录名推断表 | `governance` |
| 目录名推断表 | `ai-code→backend`、`ai-design→docs`、`ai-requirement→governance`、`ai-concise→docs`、`ai-codeHealthMind→test`、`ai-skill-mcp-Y→governance` | 未知 → `governance` |
| `load_mode` | skill.yaml.loading.mode > `disable-model-invocation: true`→`on-demand` | `always` |
| `risk` / `destructive` | frontmatter > skill.yaml.risk | `low` / `false` |
| `status` | status-overrides > (manifest 记录 ∧ bundled)→`verified` | `testing` |
| `score` | `.skillmind/scores.json` | `null` |
| `tags` / `triggers` | skill.yaml 声明 ∪ `derive_tags`/`derive_triggers` | 空数组 |

冲突时**显式声明 > 启发式**：`skill.yaml` 是技能自我声明，优先级高于 frontmatter 推断。

---

## 7. overlap（重叠检测）

判定：`tags(a) ∩ tags(b) ≥ 2` **或** `keywords(a) ∩ keywords(b) ≥ 3`。
`keywords` = description 的拉丁词（≥4 字符，去停用词）+ 中文二字滑窗。

| severity | 条件 |
|---|---|
| `warn` | 共享标签 ≥ 3（高概率职责重叠，优先审 MERGE） |
| `info` | 其余（多为 `Not for ...` 反向引用造成的噪声，如 `ai-code` 出现在他人 description 里） |

```
overlap 只提示候选，不是判决。删除/合并必须走 §3.4 生命周期，且 90 天不用的灾备/事故/迁移类 skill 仍是 P0。
```

---

## 8. 命令用法

```bash
# 生成（写 <repo>/.skillmind/registry.json，并打印人类可读摘要）
python3 skills/ai-skill-mcp-Y/scripts/registry_build.py --root .
# 机器可读
python3 skills/ai-skill-mcp-Y/scripts/registry_build.py --root . --json
# 改输出路径
python3 skills/ai-skill-mcp-Y/scripts/registry_build.py --root . --out /tmp/registry.json

# 契约自检（零依赖最小 JSON Schema 子集校验器）
python3 skills/ai-skill-mcp-Y/scripts/manifest_validate.py \
  --path skills/ai-skill-mcp-Y/skill.yaml --json
python3 skills/ai-skill-mcp-Y/scripts/manifest_validate.py \
  --path .skillmind/registry.json --schema skills/ai-skill-mcp-Y/schemas/registry.schema.json
```

| 退出码 | 含义 |
|---|---|
| 0 | 生成成功 / 校验通过 |
| 1 | 校验失败（manifest_validate 专用） |
| 2 | 用法或环境错误（root 不存在、缺 `skills/`、schema 非法 JSON、文档解析失败） |

裸 Python 3.9+（无 PyYAML）可运行：YAML 回落 `_yaml_lite`，哈希与解析全部复用 `_common`。

---

## 9. 常见坑

| 坑 | 后果 | 正解 |
|---|---|---|
| 手改 `registry.json` | 下次生成即被覆盖；路由读到幽灵 skill | 改源（SKILL.md / skill.yaml / 控制面）后重跑 |
| 把 `.skillmind/` 放进 `artifact_path` | `content_hash` 抖动 → 假 DRIFT | 生成物留在仓根状态目录 |
| 自实现 hash | 与控制面语义漂移 | 只用 `_common.hash_tree` / `hash_file` |
| 用 `skill_id` 当可变字段 | 路由历史、评分记录断链 | `skill_id` = 目录名，禁改 |
| 无 MCP 清单却编造 `mcps[]` | 路由暴露不存在的工具 | 无清单就输出 `[]` |
| `score` 缺记录填 0/100 | 掩盖事实（§15 反模式） | `null` + 原始指标另存 |
| `overlap` 命中即删 skill | 误删灾备/事故/迁移类 P0 | 只提示；`DISABLE-CANDIDATE` 也**禁自动删** |
| 让 `verified` 覆盖 `blocked` | 安全一票否决失效 | `blocked` 由人工解除，优先级最高 |
| 用 `root_words` 当 `wc -w` | 中文按字计，口径不同 | 只用于同口径横向比较 |

---

## 10. 禁 / STOP

```
禁: 手改 registry.json / scores.json / telemetry.jsonl
禁: 反向改写 shared/ 与 deploy.bundle.yaml（控制面只读）
禁: 自实现 YAML 解析或哈希（必须走 _common）
禁: 用 skill.yaml 取代 SKILL.md 根文档
禁: 无依据填 owner / score / version / mcps
STOP: registry 与 release-manifest 哈希不一致时继续发布 —— 先定位 DRIFT 根因
STOP: 依据 overlap 直接删除或合并 skill —— 走生命周期 + 人工确认
```
