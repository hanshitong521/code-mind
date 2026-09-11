# DRIFT_REPORT — Peak v3 P0 验收
schema_name: drift-report
schema_version: 1
generated_at: 2026-09-10
control_plane: ai-programming-docs
control_plane_path: E:\AAAAAA\ai-restriction-document\3、本人编程文档测试

## 1. 检测范围

| 层 | 路径 | 说明 |
|----|------|------|
| canonical (local) | `<control_plane>/skills/*` | 本仓即 canonical（CANONICAL_LOCAL） |
| canonical (external) | `E:\workA\A-skill\{requirement-mind,concise-mind}` | 外部 canonical 仓 |
| release | `<control_plane>/skills/*` | 发布副本 |
| installed | `C:\Users\Administrator\.cursor\skills` | 业务侧安装副本 |

## 2. 结论汇总（canonical vs release）

```
PASS=4 DRIFT=1 MISSING=0 UNTRACKED=0
```

| skill | 层 | 结论 | 证据 |
|-------|----|------|------|
| ai-code | canonical_vs_release | PASS | canonical == release |
| ai-design | canonical_vs_release | PASS | canonical == release |
| ai-debug | canonical_vs_release | PASS | canonical == release |
| ai-requirement | canonical_vs_release | PASS | canonical == release [SKILL.md] |
| **ai-concise** | canonical_vs_release | **DRIFT** | canonical `sha256:eaea50a1…` != release `sha256:15f69139…` |

## 3. DRIFT 详情与裁决（不静默覆盖，§6.2 / I-02）

### DRIFT-001 — ai-concise 与 concise-mind canonical 内容不一致

- **canonical**：`E:\workA\A-skill\concise-mind\SKILL.md`
  - `name: concise-mind`，描述为 `/concise-mind` overlay（lazy diffs + terse speech）
  - 归一化哈希 `sha256:eaea50a165df131963b4b54dc4840d5ff5aa04060606c66b85983e0d458a9598`
- **release**：`<control_plane>\skills\ai-concise\SKILL.md`
  - `name: concise-mind`，但内容为另一套 "write less code / be concise" 技能
  - 归一化哈希 `sha256:15f6913907cf717c0721edbcf6929374b49b08615e9b2c4affee1ac80b647488`

**判定**：两者共享 `name: concise-mind` 但正文不同 → 命中 I-10（Skill 单一 canonical source）与 I-01（单一权威拥有者）。

**修复路径（三选一，必须显式选择）**：

1. 若 canonical 为准 → `python scripts/build_release.py`（用 canonical 覆盖发布副本）
2. 若发布副本为准 → 改 `concise-mind/SKILL.md` 后重跑 `build_release.py`（supersede canonical）
3. 若两者本就不同技能 → 改 `skills/ai-concise/SKILL.md` 的 `name`，并在 manifest 断开 vendored 关系

> ⚠ 本报告不自动执行任何修复。修复属破坏性操作，需二次确认。

## 4. installed 层（release vs installed）

```
PASS=0 DRIFT=0 MISSING=3
```

| skill | 结论 | 说明 |
|-------|------|------|
| ai-code | MISSING | 未安装（`.cursor\skills` 无此目录） |
| ai-design | MISSING | 未安装 |
| ai-debug | MISSING | 未安装 |
| ai-concise | （未评估） | 安装副本命名为 `concise-mind`，与 skill key `ai-concise` 不匹配 → 见 §5-① |

当前 `C:\Users\Administrator\.cursor\skills` 实际内容：`concise-mind` 目录 + 若干 `.xxx-installed-version` 标记文件。

## 5. 已知建模缺口（P0 记录，列为后续项）

1. **installed 目录名映射**：installed 层用 `installed/<skill-key>` 定位，但实际安装名可能是 canonical 的 `name`（如 `concise-mind`）。建议在 manifest 增补 `install_name` 字段。
2. **vendored 树的比较面**：`ai-requirement` 发布副本含 36 个文件，canonical 仅 `SKILL.md`；已通过 `compare.mode: single_file` 修正（原为假 DRIFT）。
3. **`.idea/` 混入发布副本**：`skills/ai-requirement/.idea/*`（5 个文件）为 IDE 私有文件，不应进发布副本。建议加入 `hash.normalize.exclude` 或删除。

## 6. 验收命令回放

```powershell
$py = 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
$root = 'E:\AAAAAA\ai-restriction-document\3、本人编程文档测试'

& $py "$root\scripts\build_release.py"    --root $root --check   # exit 0
& $py "$root\scripts\validate_bundle.py"  --root $root           # exit 0, PASS
& $py "$root\scripts\verify_skill_drift.py" --root $root --canonical-root 'E:\workA\A-skill'  # exit 1 (ai-concise DRIFT)
& $py "$root\scripts\selftest_p0.py"                             # exit 0, PASS=14 FAIL=0
```
