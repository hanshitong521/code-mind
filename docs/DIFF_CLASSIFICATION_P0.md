# 未提交改动分类报告（P0 前置）

- 仓库：`gitee.com/yuchengq/ai-restriction-document`
- 目标目录：`3、本人编程文档测试/`（= ai-programming-docs Control Plane 本体）
- 基线：HEAD = `3fc5148`
- 生成时间：2026-09-10
- 原则：**不 commit、不回滚、不覆盖已有改动**。只做分类，供 P0 合并决策。

---

## 0. 结论摘要

| 项 | 值 |
|---|---|
| modified 文件数 | 9（+ `.idea/vcs.xml` 与本仓无关） |
| 总删除行 | -959 |
| 总新增行 | +109 |
| **判定** | **9 个文件全部属于 B 类（与发布体系冲突），且其中多数是"退化式覆盖"** |
| A 类（无关优化，保留） | 2 项：`skills/ai-code/SKILL.md` 的一行补充、`.gitignore` 的忽略规则 |
| B 类（冲突，重点合并） | 7 项 |
| C 类（重复实现，删除） | 0 项 |

### 关键发现（必须先纠正的认知）

你提到这些改动"很可能是之前 AI 已经优化过，例如 ai-code v8 / ai-design v6"。**实际 diff 显示相反**：
这些未提交改动是把**已提交的丰富 SSOT 大幅删减为最小 stub**，净删除 959 行。典型如：

- `shared/core.md`：423 行 → **7 行**（五层 pipeline 契约、六条公理、术语表、假阳性清单全删）
- `shared/handoff-schema.yaml`：176 行 → **28 行**（三种 Handoff 全字段契约 + common_constraints 全删）
- `domain-packs/java8/INDEX.md`：33 行 → **5 行**（P3C / SpotBugs / CPD / ArchUnit 工具链全删）
- `skills/ai-design/SKILL.md`：67 行 → **22 行**（G-pre/G0–G5 全部 gate、STOP 清单全删）
- `scripts/validate_handoff.py`：305 行 → 约 60 行（校验能力大幅收窄）

**因此："保留未提交改动"与"完成 P0"是冲突的**。若照单保留，P0 会把发布体系建在一堆被掏空的契约废墟上。详见 §3 决策建议。

---

## 1. 逐文件分类

| # | 文件 | 变化 | 分类 | 说明 |
|---|---|---|---|---|
| 1 | `skills/ai-code/SKILL.md` | +1 行 | **A（保留）** | 新增一行：`改Java/Mapper前:get_change_context(...)`；踩坑 `save_bug_memory`；收尾 `record_task_outcome`。是有价值的流程补充，且不碰发布面。 |
| 2 | `.gitignore` | +5 行 | **A（保留）** | 忽略 `.codeartsdoer/`、`.codegraph/`、`.merkle-snapshot.json`。本机索引不入库，正确。 |
| 3 | `deploy.bundle.yaml` | -18/+10 | **B（重点合并）** | 见 §2.1。**最关键**：`skills` 列表新增 `ai-requirement`、`ai-concise`（与 §1.1 审计一致），但**同时删掉了 `version`、`package`、以及 6 个 legacy_skill_names**（`ask-matt`/`handoff`/`skill-meta`/`java-spec`/`agent-runtime`/`session-hygiene`）。删 legacy 会导致这些旧 skill 卸载不干净。 |
| 4 | `shared/core.md` | -423/+7 | **B（冲突，禁止保留现状）** | 五层 pipeline 契约、六条公理、SSOT 表、执行铁律、反模式速查、术语表、假阳性清单 F1–F10、漏检 M1–M10、skill-encoding 规范 —— 全部删除。**这直接违反 spec §7.4 与本仓 SSOT 定位。** |
| 5 | `shared/handoff-schema.yaml` | -176/+28 | **B（冲突）** | 三种 Handoff（design_to_code / design_to_test / code_to_test / test_to_design）的完整字段契约、enum 约束、common_constraints 全删，退化为"required_any + 两个 transition 的必填名列表"。**§30 要求 schema 必须带 `schema_name` + `schema_version`，现状两者都没有。** |
| 6 | `scripts/validate_handoff.py` | -305/+60 | **B（冲突）** | 校验逻辑大幅收窄。新版本只查"必填字段是否缺失 + 验证档位 enum"，丢掉了原版的 pattern 校验、enum 校验、`_transition` 分发等能力。P0 的 `validate_bundle.py` 必须与它协调，不能各写一套。 |
| 7 | `domain-packs/java8/INDEX.md` | -33/+5 | **B（冲突）** | 整份 JDK8 质量门工具链（P3C / google-java-format / Error Prone / SpotBugs / PMD-CPD / ArchUnit / OpenRewrite / dependency:analyze / EXPLAIN）被删成 3 行占位。这是本仓唯一的 Java 领域包内容。 |
| 8 | `skills/ai-design/SKILL.md` | -67/+22 | **B（冲突）** | `version: 5.0.0` 被删、`disable-model-invocation: true` 被删、`encoding/ssot/contract/trig/axiom` 元数据行全删、G0–G5 gate 与 STOP 清单全删。**与本仓"SKILL.md = 索引 + 最小执行清单，细则在 references"的分层约定不符**：细则文件 `references/refs.md` 仍在，但 SKILL 已不再指向 gate。 |
| 9 | `skills/ai-debug/VERSION` | `1.1.0` → 空 | **B（冲突）** | 版本号文件被清空。**这恰好是 P0 要解决的问题**：release-manifest 需要读取每个 skill 的版本/哈希，空 VERSION 会让 manifest 生成失败或产出空值。 |

---

## 2. 重点合并项细节

### 2.1 deploy.bundle.yaml —— 合并策略

现状（工作区）：

```yaml
skills:
  - ai-design
  - ai-code
  - ai-debug
  - ai-requirement      # 新增，正确
  - ai-concise          # 新增，正确
legacy_skill_names:
  - ai-verify           # 只剩这一个
install_shared: true
```

已提交版（HEAD）多出：`version: 1`、`package: three-skills`，以及 legacy：`ask-matt`、`handoff`、`skill-meta`、`java-spec`、`agent-runtime`、`session-hygiene`。

**合并建议**：保留新版 `skills` 列表（5 个 skill 与 §1.1 审计一致，且与目录实际内容相符），**恢复 `version`/`package` 元数据与全部 legacy_skill_names**，并按 P0 增补 `release_manifest` 引用字段。

### 2.2 为什么不能"照单保留未提交改动"

| 若保留现状 | 后果 |
|---|---|
| `core.md` 只剩 7 行 | 所有 skill 的 `ssot:../../shared/core.md` 指向空壳；五层职责契约丢失 |
| `handoff-schema.yaml` 只剩必填名 | `validate_handoff.py` 的 enum/pattern 校验无依据；跨 Agent 交接契约不可机器校验 |
| `ai-debug/VERSION` 为空 | release-manifest 无法生成有效 `content_hash`/`version` |
| `java8/INDEX.md` 只剩 3 行 | domain-pack 名存实亡 |

这与 spec §33 硬指令 3「已存在能力优先复用；不要重新实现」和 §2.2「不追求一次性大重构」直接冲突。

---

## 3. 决策建议（待用户确认，不擅自执行）

建议采用 **"恢复契约 + 叠加 P0"** 策略，而非二选一：

1. **A 类**：原样保留（ai-code 一行补充、.gitignore 三条忽略）。
2. **B 类·恢复**：把 `core.md`、`handoff-schema.yaml`、`java8/INDEX.md`、`ai-debug/VERSION` 恢复到 HEAD 丰富版本，**因为它们是 SSOT，不能被掏空**。
3. **B 类·叠加**：在恢复后的版本上，按 spec §30 给 `handoff-schema.yaml` 加 `schema_name`/`schema_version`（向后兼容，只增不删）。
4. **B 类·合并**：`deploy.bundle.yaml` 取"新版 skills 列表 + 旧版元数据与 legacy 列表"的并集；`validate_handoff.py` 以能力更全的 HEAD 版为基线，P0 新脚本 `validate_bundle.py` 独立实现、不重叠。
5. **ai-design/SKILL.md**：恢复到含 gate 的版本（其 `references/refs.md` 仍在，恢复后索引才有效），P0 不动其内容。

> ⚠️ 以上均涉及**覆盖工作区文件**，属不可逆操作。执行前需你显式确认第 3 步的恢复范围。
> 本报告只做分类，未改动任何文件。

---

## 4. DRIFT_REPORT（本仓 vs spec）

```yaml
type: DRIFT_REPORT
repo: ai-restriction-document (3、本人编程文档测试 = ai-programming-docs)
revision: 3fc5148 + working-tree
spec_section: §1.6 / §13 / §6.2 / §30 / §33
observed:
  path: shared/core.md
  behavior: 工作区版本为 7 行 stub，已提交版本为 423 行 SSOT
conflict:
  expected: 共享契约作为本仓 SSOT 稳定存在，供各 skill 的 ssot: 指针消费
  actual: 工作区未提交改动将其删减为 7 行，所有 ssot:../../shared/core.md 指针指向空壳
impact:
  - P0 的 release-manifest 无法为共享契约生成有效哈希基线
  - 跨 Agent Handoff 契约不可机器校验
  - domain-pack java8 名存实亡
recommended_resolution:
  keep_existing_and_update_spec: false
  migrate_code_to_spec: true   # 恢复契约丰富版，再叠加 P0 字段
evidence:
  - git diff shared/core.md            # -423/+7
  - git diff shared/handoff-schema.yaml # -176/+28
  - git diff skills/ai-debug/VERSION    # 1.1.0 -> 空
```

```yaml
type: DRIFT_REPORT
repo: ai-restriction-document (3、本人编程文档测试 = ai-programming-docs)
revision: 3fc5148
spec_section: §30 API/Schema 版本策略
observed:
  path: shared/handoff-schema.yaml
  behavior: 契约文件无 schema_name / schema_version 字段
conflict:
  expected: §30 要求所有跨仓 JSON/YAML 契约必须声明 schema_name + schema_version
  actual: 现网 handoff-schema.yaml 只有 version: 1（且仅存在于工作区 stub 版）
impact:
  - Consumer 无法判断支持版本；不认识 major 时无法 BLOCKED
recommended_resolution:
  keep_existing_and_update_spec: false
  migrate_code_to_spec: true
evidence:
  - Read shared/handoff-schema.yaml (HEAD 版第 1-30 行)
```
