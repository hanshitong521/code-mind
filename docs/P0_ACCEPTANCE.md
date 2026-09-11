# P0 验收结果 — Peak v3 Engineering Control Plane

> 项目：AI Engineering OS Peak v3.0 — P0「Canonical Source → Release → Derived Copy」
> 控制面：`ai-programming-docs`（`E:\AAAAAA\ai-restriction-document\3、本人编程文档测试`）
> 验收时间：2026-09-10 15:26
> 验收环境：Windows / PowerShell · Python 3.13.14 (venv) · PyYAML 6.0.3

---

## 一、交付清单（10 项要求 → 全部落地）

| # | 要求 | 交付物 | 状态 |
|---|------|--------|------|
| 1 | release-manifest.yaml | `shared/release-manifest.yaml` | ✅ |
| 2 | capability-registry.yaml | `shared/capability-registry.yaml` | ✅ |
| 3 | schema-versions.yaml | `shared/schema-versions.yaml` | ✅ |
| 4 | verify_skill_drift.py | `scripts/verify_skill_drift.py` | ✅ |
| 5 | validate_bundle.py | `scripts/validate_bundle.py` | ✅ |
| 6 | build_release.py | `scripts/build_release.py` | ✅ |
| 7 | install.ps1 hash 校验 | `install.ps1`（`Invoke-HashVerify`） | ✅ |
| 8 | backup | `install.ps1`（`New-InstallBackup`） | ✅ |
| 9 | rollback | `install.ps1`（`Invoke-Rollback`） | ✅ |
| 10 | doctor 检查 | `install.ps1`（`Invoke-Doctor`） | ✅ |

辅助件：`scripts/_release_lib.py`（统一哈希/归一化，避免多脚本算法分叉）、`scripts/selftest_p0.py`（自测套件）、`docs/DRIFT_REPORT.md`、`docs/DRIFT_REPORT.json`。

---

## 二、验收门（G1–G5）

| 门 | 命令 | 期望 | 实测 | 结果 |
|----|------|------|------|------|
| G1 | `build_release.py --check` | exit 0 | exit 0，10 项哈希 OK | ✅ |
| G2 | `validate_bundle.py` | exit 0 / PASS | exit 0 / PASS（5 skills·12 caps·6 contracts） | ✅ |
| G3 | `verify_skill_drift.py --canonical-root` | exit 1（仅 ai-concise DRIFT） | exit 1，PASS=4 DRIFT=1 | ✅ |
| G4 | `selftest_p0.py` | exit 0 / 14 PASS | exit 0 / PASS=14 FAIL=0 | ✅ |
| G5 | `install.ps1 -Doctor`（未安装） | exit 1 | exit 1，缺失 6 项 | ✅ |

---

## 三、核心结论

### 3.1 三层漂移检测真实生效

- 层 1（canonical vs release）：**4 PASS + 1 DRIFT**
- 层 2（release vs installed）：正确识别未安装状态
- 层 3（UNTRACKED）：磁盘有但 manifest 未声明 → 可检出

### 3.2 唯一真实 DRIFT（需人工裁决，不自动修复）

**ai-concise** 的发布副本 `skills/ai-concise/SKILL.md` 与外部 canonical
`E:\workA\A-skill\concise-mind\SKILL.md` 内容不一致：

- canonical 归一化哈希：`sha256:eaea50a1…`
- release 归一化哈希：`sha256:15f69139…`

两者共用 `name: concise-mind` 但正文是两套不同技能 → 命中 **I-10（Skill 单一 canonical source）**。
裁决路径见 `docs/DRIFT_REPORT.md` 第 3 节（三选一，需显式确认）。

---

## 四、过程中发现并修复的缺陷

| 缺陷 | 性质 | 修复 |
|------|------|------|
| 外部 canonical 路径解析漏掉仓目录段（`root/SKILL.md` 应为 `root/<repo>/SKILL.md`） | 逻辑 bug | 新增 `_resolve_external_canonical()`，优先 `external_sources.local_path`，回退 `source_repo` 末段 |
| vendored 整树 vs canonical 单文件比较导致**假 DRIFT** | 建模缺口 | 新增 `compare.mode: single_file`（含 `canonical_file`/`release_file`） |
| **`-ProjectPath` 被忽略，静默安装到用户级 `.cursor\skills`** | 安全 bug（高危） | 检测到 `-ProjectPath` 而 `-Target` 未显式指定时，自动推断为 `project` 并打日志 |
| rollback 会清 legacy 名单（可能误删用户既有内容） | 安全 bug（高危） | 清理范围收窄至 `$Bundle.Skills`；用户级 rollback 需 `-Confirm`/`-Force`；`manifest.txt` 空快照也写盘 |

---

## 五、安全变更审计

以下用户级路径在过程中被**误建后又清理**，现已还原：

- `C:\Users\Administrator\.cursor\skills\` 曾出现 5 个 junction（ai-code / ai-design / ai-debug / ai-requirement / ai-concise）→ 已全部移除链接，**canonical 目标文件毫发无损**（2/3/2/36/3 文件数校验通过）。
- 现用户级目录仅保留原有：`concise-mind` + 11 个 `.xxx-installed-version` 标记。

**未触碰**：requirement-mind、project-brain-agent、Token-Mind、test-Mind、concise-mind 五仓（本次仅读取，未写入）。

---

## 六、已知遗留（列为 P0 记录 / 后续项）

1. **installed 目录名映射**：`concise-mind` 安装名与 skill key `ai-concise` 不一致 → 建议 manifest 增 `install_name`。
2. **`.idea/` 混入发布副本**：`skills/ai-requirement/.idea/*`（5 文件）不应进发布副本 → 建议删除或加 `hash.normalize.exclude`。
3. ai-concise DRIFT **尚未裁决**（等玉斌确认以哪边为准）。

---

## 七、复现命令

```powershell
$py   = 'C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe'
$root = 'E:\AAAAAA\ai-restriction-document\3、本人编程文档测试'

& $py "$root\scripts\build_release.py"       --root $root --check
& $py "$root\scripts\validate_bundle.py"     --root $root
& $py "$root\scripts\verify_skill_drift.py"  --root $root --canonical-root 'E:\workA\A-skill'
& $py "$root\scripts\selftest_p0.py"

# 安装（项目级，安全）
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\install.ps1" -ProjectPath 'D:\myproj'
# 回滚（项目级）
& powershell -NoProfile -ExecutionPolicy Bypass -File "$root\install.ps1" -Rollback -Target project -ProjectPath 'D:\myproj'
```
