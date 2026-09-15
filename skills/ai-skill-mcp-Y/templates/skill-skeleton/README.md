# skill-skeleton — 可直接复制使用的 Skill 骨架

> 规格：`references/spec-v2.md` §8 Skill 开发规范、§5 三级加载 ｜ 元数据：`references/spec-v1.md` §17 ｜ 验证：`references/testmind.md`
> 本目录**只做起点**：拷走 → 改名 → 替换占位符 → 填真内容。禁把骨架原样留在仓库里当已完成的 skill。

## 1 用法（5 步）

```bash
# 1 复制到 skills/ 下（目录名 = skill_id，稳定后禁改）
cp -r skills/ai-skill-mcp-Y/templates/skill-skeleton skills/<SKILL_NAME>

# 2 替换占位符（见 §2），删除不适用的行

# 3 建目录（按需，不空建）
mkdir -p skills/<SKILL_NAME>/{references,templates,scripts,tests,benchmark}

# 4 校验 manifest（统一 CLI 等价形式：skillmind.py manifest validate --path ...）
python skills/ai-skill-mcp-Y/scripts/manifest_validate.py --path skills/<SKILL_NAME>/skill.yaml

# 5 入注册表并核对派生字段
python skills/ai-skill-mcp-Y/scripts/registry_build.py --root . --json
```

第 4 步在**替换占位符之前必然 FAIL**（`id` 含 `<>` 不符合 pattern），这是预期；替换后应 PASS（0 errors）。

`registry build` 会从 `SKILL.md` 派生 `root_lines` / `root_words` / `tags` / `triggers`，从文件系统派生 `path` / `dir` / `refs`；**这些字段不要在 `skill.yaml` 里重复声明**。

## 2 替换点

| 占位符 | 出现位置 | 取值要求 | 禁 |
|---|---|---|---|
| `<SKILL_NAME>` | `SKILL.md` frontmatter `name`、正文标题、`skill.yaml.id` | 与目录名一致；小写 + 连字符；稳定后禁改 | 中文名、带空格、带版本号 |
| `<TRIGGER>` | `SKILL.md` frontmatter `description` 的 `Use when`、`trig:` 行、`何时用:`、`skill.yaml.triggers.include` | 用户真实会说的话（原话词 + `/slash`）；2–6 个 | 领域宽词（「数据库相关」「代码相关」） |
| `<STOP_LIST>` | `SKILL.md` frontmatter `description` 的 `Not for`、`何时不用:`、`STOP:` 行首、`skill.yaml.triggers.exclude` | 最易误触发的邻域 + 交给谁 | 留空 |
| `<OWNER>` | `skill.yaml.owner` | 能力域标识（对齐 `../../shared/capability-registry.yaml`） | 写个人姓名 |

另需按实际改动：`skill.yaml.category`（默认 `backend`，枚举 `backend|frontend|data|infra|governance|docs|test`）、`tags`、`cost.runtime_class`（`cheap|standard|expensive`）、`risk.level` / `risk.destructive`、`loading.mode`、`security_permissions`。

替换后自检：`description` 是否**只回答「现在要不要加载我」**，且 ≤1 行、无工作流摘要（V1 §7.1、§22.2）。

## 3 路径约定

- 骨架内 `../../shared/core.md`、`../../shared/handoff-schema.yaml` 按**复制目标** `skills/<SKILL_NAME>/` 解析，复制后即成立。
- 骨架内 `references/`、`templates/`、`scripts/`、`tests/`、`benchmark/` 均相对**本 skill 根**。
- 跨仓/控制面只读消费的路径写在 `../../shared/` 下；禁写绝对路径、禁写个人机器路径。

## 4 目录与尺寸

```
skills/<SKILL_NAME>/
├─ README.md          # 人读入口
├─ SKILL.md           # 根路由器（≤120 行）
├─ skill.yaml         # 统一 manifest（§17）
├─ references/        # 深层参考（命中才读，一文件一主题）
├─ templates/         # 产出模板
├─ scripts/           # 可执行工具（零第三方依赖）
├─ tests/             # trigger 四类 + 用例
└─ benchmark/         # 基准任务与基线
```

| 对象 | 预算 | 超限动作 |
|---|---|---|
| L0（`name`+`description`+`tags`+`score`） | ≤100 tokens | 改窄 `description`，禁删 `Not for` |
| 根 `SKILL.md` | 高频常驻 <200 words；普通 <500 words；硬顶 ≤120 行 | 移入 `references/` |
| 单条 reference | ≤2000 tokens | 再拆，或改由 `scripts/` 预处理 |

**禁为拆而拆**：一次任务要读 ≥5 个碎文件 = 失败，合回去。口径见 `references/token-loading.md`、`references/apply.md`。

## 5 交付前检查

- [ ] `name` 与目录名一致；`description` 含 `Use when` + `Not for`，≤1 行
- [ ] `trig:` / `load:` / `axiom:` / `G0–Gn` / `ref:` / `STOP:` 六类行齐（house DSL）
- [ ] `ref:` 每条一行「信号 → 路径」，命中单读，禁批读
- [ ] `skill.yaml` 必填字段齐（`schemas/skill-manifest.schema.json` = spec §17 的机读形式），不适用的可选字段删掉而非留空
- [ ] `manifest validate` PASS（0 errors）；`registry build` 里 `root_lines` 未超限
- [ ] trigger 四类用例已写（`tests/trigger-cases.md`），P/N/B/C 各 ≥1
- [ ] 四类测试与上线门槛见 `references/testmind.md` §4，报告用 `templates/skill-score-report.md`
- [ ] 改动留 `templates/evolution-log.md` 一条（含回滚点）

## 6 禁

禁: 原样保留骨架不填|留 TBD/待补充|description 写工作流|description 留领域宽词|`<STOP_LIST>` 留空|`skill.yaml` 重复声明 registry 派生字段|根文档塞参考资料|写绝对路径|为空目录硬造 references 碎文件|自动删除资源|无回滚点上线|只报压缩率
