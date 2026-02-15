# Identity Drift CI/CD Lab (GitHub Actions OIDC)

Laboratorio reproducible para medir y demostrar fallos de *identity binding* en CI/CD (identity drift / token confusion) usando tokens OIDC reales emitidos por GitHub Actions. El objetivo no es “weaponizar”, sino mostrar qué invariantes se rompen cuando la validación es laxa.

## Qué demuestra

- Un token puede ser criptográficamente válido y aun así ser inseguro fuera de su contexto: la firma prueba autenticidad, no intención.
- `job_workflow_ref` es una frontera del control-plane (H3): evita sustitución de workflows dentro del mismo repo.
- `aud` es *purpose binding* (H4): evita que un token válido sea reutilizable entre consumidores.

Invariantes mínimas recomendadas para consumidores: `iss`, `aud`, `repository`, `event_name`, `ref`, `job_workflow_ref` (+ `environment` si aplica).

## Layout (core)

- `app/consumer.py`: FastAPI consumer (`/introspect`, `/policies`, `/health`)
- `app/policies.py`: políticas LAX vs STRICT (env vars)
- `scripts/decode_and_diff.py`: diff local de `result.json`
- Workflows:
  - `.github/workflows/01-push.yml`
  - `.github/workflows/02-pr.yml`
  - `.github/workflows/05-alt.yml`
  - `.github/workflows/03-dispatch.yml` (mantener para H4)
- AWS trust policies (versionadas):
  - `aws/trust-lax-final.json`
  - `aws/trust-strict-v1-final.json`
  - `aws/trust-strict-v2-final.json`

## Consumer (local)

```bash
cd /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/app
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

GitHub Actions llama a `secrets.CONSUMER_URL`:
- si es `https://<host>`, el workflow agrega `/introspect`
- si es `https://<host>/introspect`, se usa tal cual

## Hipótesis (publicables)

**H3 — Workflow Ref Binding**
Si el consumidor no fija `job_workflow_ref`, cualquier workflow del repo con `id-token: write` puede emitir tokens “equivalentes”, colapsando el control-plane en autoridad ambiente.

**H4 — Audience Binding (Purpose Binding)**
Si el consumidor no valida `aud`, un token válido puede ser aceptado fuera de su propósito previsto, convirtiéndose en una capacidad reutilizable entre consumidores.

## Experimentos (Fase 1: Consumer propio)

### H3: Workflow Ref Binding

Config del consumer (pin a solo `01-push`):

```bash
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/01-push.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Trigger: push a `main` (corren `01-push` y `05-alt`).

### H4: Audience Binding (un solo knob)

Config del consumer (pin a `03-dispatch`):

```bash
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/03-dispatch.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Trigger (dos ejecuciones, mismo workflow, distinta audience):

```bash
unset GITHUB_TOKEN GH_TOKEN
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=ci-oidc-lab
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=other-service
```

## AWS (Fase 2: IAM real)

Objetivo: reproducir el mismo patrón en IAM (LAX vs STRICT) con GitHub OIDC -> STS.

Trust policies:
- LAX: `aws/trust-lax-final.json` (wildcard repo)
- STRICT v1: `aws/trust-strict-v1-final.json` (pin `aud` + `sub` a `refs/heads/main`)
- STRICT v2: `aws/trust-strict-v2-final.json` (v1 + pin `job_workflow_ref` a `01-push`)

Nota: un STRICT v3 con `event_name == push` se probó y rompió incluso `01-push` (STS AccessDenied), por lo que no se mantiene en el repo.

## Evidencia (run IDs)

### Fase 1 (Consumer)

H3 (push/main, workflow pin):
- `01-push` STRICT OK: run `22022405651`
- `05-alt` STRICT FAIL (workflow_ref): run `22022405649`

H4 (mismo workflow/ref/event, cambia solo `aud`):
- `03-dispatch` (`audience=ci-oidc-lab`) STRICT OK: run `22022467100`
- `03-dispatch` (`audience=other-service`) STRICT FAIL (`aud_not_allowed`): run `22022467170`

### Fase 2 (AWS IAM, STRICT v2)

- push/main `01-push` OK (AssumeRoleWithWebIdentity + ListBucket): run `22033604517`
- push/main `05-alt` DENIED (STS AccessDenied): run `22033604526`
- PR `02-pr` DENIED (STS AccessDenied): run `22033644786`

Ver logs / artifacts:

```bash
unset GITHUB_TOKEN GH_TOKEN
gh run view -R scumfrog/Identity_Drift_CICD <RUN_ID> --log
gh run download -R scumfrog/Identity_Drift_CICD <RUN_ID>
```

## Diffs local (claims / context)

```bash
python3 /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/scripts/decode_and_diff.py <A.json> <B.json>
```

