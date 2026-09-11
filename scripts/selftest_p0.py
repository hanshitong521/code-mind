#!/usr/bin/env python3
"""selftest_p0.py — P0 发布控制面确定性自测

覆盖：
  A. build_release.py 幂等性（同内容两次构建哈希一致）
  B. verify_skill_drift 四种结论（PASS / DRIFT / MISSING / UNTRACKED）
  C. validate_bundle 一致性与负例（legacy 重叠、非法 owner、缺文件）
  D. 跨平台归一化（CRLF vs LF 同哈希）

运行：python scripts/selftest_p0.py
退出码：0=全通过；1=有失败
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

PASSED = 0
FAILED = 0


def check(name: str, cond: bool, extra: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  [OK]   {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name}" + (f" — {extra}" if extra else ""))


def run(args: list[str], cwd: Path | None = None) -> tuple[int, str]:
    p = subprocess.run([sys.executable, *args], cwd=str(cwd or ROOT),
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    from _release_lib import hash_tree, load_yaml, normalize_bytes  # noqa: E402

    print("== A. build_release 幂等 ==")
    c1, o1 = run(["scripts/build_release.py", "--check", "--json"])
    check("build --check 退出码 0", c1 == 0, o1[:300])
    try:
        j1 = json.loads(o1[o1.index("{"):])
    except Exception as e:
        check("build --check 输出可解析 JSON", False, str(e))
        j1 = {"skills": {}}
    c2, o2 = run(["scripts/build_release.py", "--check", "--json"])
    try:
        j2 = json.loads(o2[o2.index("{"):])
    except Exception:
        j2 = {"skills": {}}
    same = all(j1["skills"].get(k, {}).get("content_hash") ==
               j2["skills"].get(k, {}).get("content_hash") for k in j1.get("skills", {}))
    check("两次构建哈希一致（幂等）", same and bool(j1.get("skills")))

    print("== D. 跨平台归一化 ==")
    crlf = b"line1\r\nline2\r\n"
    lf = b"line1\nline2\n"
    check("CRLF 与 LF 归一化后一致",
          normalize_bytes(crlf) == normalize_bytes(lf))
    trail = b"line1   \nline2\t\n"
    check("行尾空白被剥离", normalize_bytes(trail) == normalize_bytes(lf))

    print("== B. drift 四种结论 ==")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 造一个最小假仓
        (tmp / "shared").mkdir()
        (tmp / "skills" / "s1").mkdir(parents=True)
        (tmp / "skills" / "s1" / "SKILL.md").write_text("hello\n", encoding="utf-8")
        (tmp / "shared" / "release-manifest.yaml").write_text(
            "schema_name: release-manifest\nschema_version: 1\n"
            "hash:\n  normalize:\n    exclude: []\n"
            "skills:\n"
            "  s1:\n    status: CANONICAL_LOCAL\n    artifact_path: skills/s1\n"
            "    content_hash: null\n"
            "  s2:\n    status: CANONICAL_LOCAL\n    artifact_path: skills/s2\n"
            "    content_hash: null\n"
            "shared_contracts: {}\n", encoding="utf-8")

        # 先 build 回写
        c, o = run(["scripts/build_release.py", "--root", str(tmp)])
        # build 对 s2 MISSING 会报错，这是预期
        check("build 检出 MISSING skill", c == 1 and "s2" in o, o[:200])

        # 补上 s2
        (tmp / "skills" / "s2").mkdir()
        (tmp / "skills" / "s2" / "SKILL.md").write_text("world\n", encoding="utf-8")
        c, o = run(["scripts/build_release.py", "--root", str(tmp)])
        check("补齐后 build 成功", c == 0, o[:200])

        c, o = run(["scripts/verify_skill_drift.py", "--root", str(tmp), "--json"])
        j = json.loads(o[o.index("{"):])
        check("漂移检测 PASS", j["summary"]["PASS"] >= 2 and j["summary"]["DRIFT"] == 0,
              json.dumps(j["summary"], ensure_ascii=False))

        # 制造 DRIFT（改文件不改 manifest）
        (tmp / "skills" / "s1" / "SKILL.md").write_text("tampered\n", encoding="utf-8")
        c, o = run(["scripts/verify_skill_drift.py", "--root", str(tmp), "--json"])
        j = json.loads(o[o.index("{"):])
        check("篡改后检出 DRIFT", c == 1 and j["summary"]["DRIFT"] >= 1,
              json.dumps(j["summary"], ensure_ascii=False))

        # 制造 MISSING
        shutil.rmtree(tmp / "skills" / "s2")
        c, o = run(["scripts/verify_skill_drift.py", "--root", str(tmp), "--json"])
        j = json.loads(o[o.index("{"):])
        check("删目录后检出 MISSING", j["summary"]["MISSING"] >= 1,
              json.dumps(j["summary"], ensure_ascii=False))

        # 制造 UNTRACKED
        (tmp / "skills" / "s3").mkdir()
        (tmp / "skills" / "s3" / "SKILL.md").write_text("x\n", encoding="utf-8")
        c, o = run(["scripts/verify_skill_drift.py", "--root", str(tmp), "--json"])
        j = json.loads(o[o.index("{"):])
        check("新增未声明 skill 检出 UNTRACKED", j["summary"]["UNTRACKED"] >= 1,
              json.dumps(j["summary"], ensure_ascii=False))

    print("== C. validate_bundle 正例/负例 ==")
    c, o = run(["scripts/validate_bundle.py", "--json"])
    try:
        j = json.loads(o[o.index("{"):])
        check("本仓 validate_bundle PASS", c == 0 and j["ok"], o[:300])
    except Exception as e:
        check("本仓 validate_bundle PASS", False, f"{e} {o[:200]}")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        (tmp / "shared").mkdir()
        (tmp / "skills" / "a").mkdir(parents=True)
        (tmp / "skills" / "a" / "SKILL.md").write_text("x\n", encoding="utf-8")
        (tmp / "shared" / "release-manifest.yaml").write_text(
            "schema_name: release-manifest\nschema_version: 1\nskills:\n"
            "  a:\n    artifact_path: skills/a\nshared_contracts: {}\n", encoding="utf-8")
        (tmp / "shared" / "capability-registry.yaml").write_text(
            "schema_name: capability-registry\nschema_version: 1\n"
            "capabilities:\n  cap.x:\n    owner: not-a-real-owner\n    phase: bogus\n", encoding="utf-8")
        (tmp / "shared" / "schema-versions.yaml").write_text(
            "schema_name: schema-versions\nschema_version: 1\ncontracts: {}\n", encoding="utf-8")
        # legacy 与 skills 重叠 → 必须 FAIL
        (tmp / "deploy.bundle.yaml").write_text(
            "schema_name: deploy-bundle\nschema_version: 2\n"
            "skills:\n  - a\nlegacy_skill_names:\n  - a\ninstall_shared: false\n", encoding="utf-8")
        c, o = run(["scripts/validate_bundle.py", "--root", str(tmp), "--json"])
        j = json.loads(o[o.index("{"):])
        errs = " ".join(j["errors"])
        check("检出 legacy 与 skills 重叠", not j["ok"] and "legacy_skill_names" in errs, errs[:200])
        check("检出非法 owner", "owner" in errs, errs[:200])
        check("检出非法 phase", "phase" in errs, errs[:200])

    print(f"\n结果：PASS={PASSED} FAIL={FAILED}")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
