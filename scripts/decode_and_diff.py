#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load(p: Path) -> Dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def _claims(doc: Dict[str, Any]) -> Dict[str, Any]:
    return doc.get("claims") or {}


def _ctx(doc: Dict[str, Any]) -> Dict[str, Any]:
    return doc.get("workflow_context") or {}


def _keys(d: Dict[str, Any]) -> List[str]:
    return sorted(d.keys())


def _diff(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    ka = set(a.keys())
    kb = set(b.keys())
    for k in sorted(ka | kb):
        if k not in ka:
            out.append(f"+ {k} = {b.get(k)!r}")
        elif k not in kb:
            out.append(f"- {k} = {a.get(k)!r}")
        else:
            va = a.get(k)
            vb = b.get(k)
            if va != vb:
                out.append(f"~ {k}: {va!r} -> {vb!r}")
    return out


def main(argv: List[str]) -> int:
    if len(argv) < 3:
        print("usage: decode_and_diff.py <resultA.json> <resultB.json>", file=sys.stderr)
        return 2

    a_path = Path(argv[1])
    b_path = Path(argv[2])
    a = _load(a_path)
    b = _load(b_path)

    a_claims = _claims(a)
    b_claims = _claims(b)
    a_ctx = _ctx(a)
    b_ctx = _ctx(b)

    print(f"== Claims keys: {a_path.name} ({len(a_claims)}) vs {b_path.name} ({len(b_claims)})")
    print("== Claims diff")
    for line in _diff(a_claims, b_claims):
        print(line)

    print("\n== Workflow context diff")
    for line in _diff(a_ctx, b_ctx):
        print(line)

    print("\n== Policy results (A, then B)")
    print(json.dumps(a.get("policy_results"), indent=2, sort_keys=True))
    print(json.dumps(b.get("policy_results"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

