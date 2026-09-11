#!/usr/bin/env python3
"""Validate handoff YAML blocks against shared/handoff-schema.yaml."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    print("PyYAML required: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


def load_schema(root: Path) -> dict:
    path = root / "shared" / "handoff-schema.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def validate_doc(doc: dict, schema: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["handoff must be a mapping"]
    transition = doc.get("_transition")
    if transition:
        spec = (schema.get("transitions") or {}).get(transition, {})
        for key in spec.get("required", []):
            if key not in doc or doc[key] in (None, ""):
                errors.append(f"missing required field for {transition}: {key}")
    else:
        for key in schema.get("required_any", []):
            if key in doc:
                return errors
        errors.append(f"need at least one of: {schema.get('required_any')}")
    level = doc.get("验证档位")
    if level and level not in (schema.get("verification_levels") or []):
        errors.append(f"unknown 验证档位: {level}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate handoff YAML")
    parser.add_argument("file", type=Path, help="YAML file or markdown containing ```yaml block")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    schema = load_schema(args.root)
    text = args.file.read_text(encoding="utf-8")
    if "```yaml" in text:
        text = text.split("```yaml", 1)[1].split("```", 1)[0]
    doc = yaml.safe_load(text) or {}
    errors = validate_doc(doc, schema)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
