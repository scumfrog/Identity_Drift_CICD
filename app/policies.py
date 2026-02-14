from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional


def _env_list(name: str, default: str = "") -> List[str]:
    raw = os.environ.get(name, default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


EXPECTED: Dict[str, Any] = {
    # Si lo defines, STRICT/LAX pinnean el repositorio exacto. Si no, no se valida repo (fase 1 rápida).
    "repository": os.environ.get("EXPECTED_REPOSITORY", "").strip(),
    # Si lo defines, STRICT pinnea job_workflow_ref exacto(s). Si no, no se valida workflow_ref.
    "allowed_workflows": _env_list("ALLOWED_WORKFLOWS", ""),
    "allowed_event_names": _env_list("ALLOWED_EVENT_NAMES", "push,workflow_dispatch,workflow_call"),
    "allowed_ref_regex": os.environ.get("ALLOWED_REF_REGEX", r"^refs/heads/main$"),
    "allowed_audiences": _env_list("ALLOWED_AUDIENCES", "ci-oidc-lab"),
    # Opcional: atar a environment (GitHub Environments)
    "allowed_environments": _env_list("ALLOWED_ENVIRONMENTS", ""),
}


def _get(claims: Dict[str, Any], key: str, default: Any = None) -> Any:
    return claims.get(key, default)


def _norm_aud(aud: Any) -> List[str]:
    if isinstance(aud, list):
        return [x for x in aud if isinstance(x, str)]
    if isinstance(aud, str):
        return [aud]
    return []


def evaluate_policies(claims: Dict[str, Any]) -> Dict[str, Any]:
    results: Dict[str, Any] = {}

    # Policy LAX: solo binder mínimo (ej: issuer + firma ya se validó; aquí solo repo).
    lax_ok = True
    lax_reasons: List[str] = []
    repo = _get(claims, "repository")
    if EXPECTED["repository"] and repo != EXPECTED["repository"]:
        lax_ok = False
        lax_reasons.append(f"repository_mismatch: {repo}")
    results["LAX"] = {"ok": lax_ok, "reasons": lax_reasons}

    # Policy STRICT: ata invariantes de contexto relevantes.
    strict_ok = True
    strict_reasons: List[str] = []

    event_name = _get(claims, "event_name")
    ref = _get(claims, "ref")
    workflow_ref = _get(claims, "job_workflow_ref") or _get(claims, "workflow_ref")
    aud_list = _norm_aud(_get(claims, "aud"))
    environment = _get(claims, "environment")  # puede no existir si no usas environments

    if EXPECTED["repository"] and repo != EXPECTED["repository"]:
        strict_ok = False
        strict_reasons.append(f"repository_mismatch: {repo}")

    if event_name not in EXPECTED["allowed_event_names"]:
        strict_ok = False
        strict_reasons.append(f"event_name_not_allowed: {event_name}")

    if not ref or not re.match(EXPECTED["allowed_ref_regex"], ref):
        strict_ok = False
        strict_reasons.append(f"ref_not_allowed: {ref}")

    if EXPECTED["allowed_workflows"]:
        if not workflow_ref or workflow_ref not in EXPECTED["allowed_workflows"]:
            strict_ok = False
            strict_reasons.append(f"workflow_ref_not_allowed: {workflow_ref}")

    if EXPECTED["allowed_audiences"]:
        if not any(a in EXPECTED["allowed_audiences"] for a in aud_list):
            strict_ok = False
            strict_reasons.append(f"aud_not_allowed: {aud_list}")

    if EXPECTED["allowed_environments"]:
        if environment not in EXPECTED["allowed_environments"]:
            strict_ok = False
            strict_reasons.append(f"environment_not_allowed: {environment}")

    results["STRICT"] = {"ok": strict_ok, "reasons": strict_reasons}

    # STRICT+: pines fuertes opcionales (ej: sha exacto) se pueden agregar aquí.
    # Mantengo el lab simple: el pin más útil suele ser workflow_ref exacto + aud exacta.
    results["STRICT_PLUS"] = {
        "ok": strict_ok,
        "reasons": list(strict_reasons),
        "note": "Placeholder: agrega checks extra (ej. job_workflow_sha) si quieres strict+ real.",
    }

    return results
