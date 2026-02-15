# Identity Drift CI/CD Lab (GitHub Actions OIDC)

Laboratorio reproducible para capturar tokens OIDC reales emitidos por GitHub Actions, inspeccionar claims y demostrar por qué una validación laxa rompe invariantes de binding (sin “weaponizar”).

## Layout

- `app/consumer.py`: FastAPI “token consumer” (`/introspect`, `/policies`, `/health`)
- `app/policies.py`: políticas LAX vs STRICT (configurables por env vars)
- `.github/workflows/*.yml`: workflows que piden OIDC y suben artifacts `result.json` + `context.json`
- `scripts/decode_and_diff.py`: diff local entre dos `result.json`

## Ejecutar el Consumer (local)

```bash
cd /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/app
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn consumer:app --host 0.0.0.0 --port 8080
```

Endpoints:

- `GET /health`
- `GET /policies`
- `POST /introspect` con header `Authorization: Bearer <OIDC_JWT>`

## Configurar políticas (STRICT)

El consumer lee env vars para evitar hardcode:

- `EXPECTED_REPOSITORY` (opcional, ej: `ORG/REPO`; si no se define, no se pinnea repo en fase 1)
- `ALLOWED_WORKFLOWS` (opcional, coma separada; valores tipo `ORG/REPO/.github/workflows/01-push.yml@refs/heads/main`; si no se define, no se pinnea workflow_ref)
- `ALLOWED_EVENT_NAMES` (ej: `push,workflow_dispatch`)
- `ALLOWED_REF_REGEX` (ej: `^refs/heads/main$`)
- `ALLOWED_AUDIENCES` (ej: `ci-oidc-lab`)
- `ALLOWED_ENVIRONMENTS` (opcional)

Ejemplo:

```bash
export EXPECTED_REPOSITORY="YOURORG/ci-oidc-lab"
export ALLOWED_WORKFLOWS="YOURORG/ci-oidc-lab/.github/workflows/01-push.yml@refs/heads/main,YOURORG/ci-oidc-lab/.github/workflows/03-dispatch.yml@refs/heads/main"
export ALLOWED_EVENT_NAMES="push,workflow_dispatch"
export ALLOWED_REF_REGEX="^refs/heads/main$"
export ALLOWED_AUDIENCES="ci-oidc-lab"
```

## Conectar GitHub Actions al Consumer

Los workflows hacen `POST` a `secrets.CONSUMER_URL`.

- Si pones `https://<tu-host>`: el workflow le agrega `/introspect` automáticamente.
- Si pones `https://<tu-host>/introspect`: se usa tal cual.

Notas:

- No se imprime el token en logs.
- En `pull_request` desde forks, GitHub puede bloquear secrets y/o la emisión de OIDC: el artifact queda con `ok=false` y `error=oidc_token_unavailable_in_this_context`.

## Diffs local

```bash
python /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/scripts/decode_and_diff.py result-push.json result-pr.json
```

## Ajuste rápido que falta (antes de correr)

Ninguno: `04-call-reusable` llama al reusable por path local.
## PR Trigger

Este repo incluye el workflow `02-pr` (evento `pull_request`) para capturar el OIDC en contexto PR y comparar contra `push`/`workflow_dispatch`.

## Demo Modes (H3/H4)

Nota: el consumer se configura por env vars al arrancar. Para que el resultado sea convincente, fija una sola variable de control por experimento.

## Hypotheses (Publishable)

### H3: Workflow Ref Binding

If the consumer does not pin `job_workflow_ref`, any workflow in the same repository with `id-token: write` can mint “equivalent” tokens, collapsing the control-plane into ambient authority.

### H4: Audience Binding (Purpose Binding)

If the consumer does not enforce `aud`, a valid token can be accepted outside its intended purpose, turning into a reusable capability across consumers (“ambient authority”).

## Findings

- A token can be valid and still be unsafe in context: signature verification proves authenticity, not intent.
- `job_workflow_ref` is a control-plane boundary: pinning workflow references prevents workflow substitution inside the same repo.
- `aud` is purpose binding, not metadata: when audience is not enforced, tokens become reusable capabilities across consumers.
- Minimal invariant set (recommended): `iss`, `aud`, `repository`, `event_name`, `ref`, `job_workflow_ref` (+ `environment` when used, + org scoping as needed).

## Experiments Summary

| Experiment | Consumer pin | Single knob | Expected outcome |
|---|---|---|---|
| H3 | `ALLOWED_WORKFLOWS=.../01-push.yml@refs/heads/main` | `job_workflow_ref` | `01-push` STRICT OK, `05-alt` STRICT FAIL |
| H4 | `ALLOWED_WORKFLOWS=.../03-dispatch.yml@refs/heads/main` | `aud` | `aud=ci-oidc-lab` STRICT OK, `aud=other-service` STRICT FAIL |

### H3: Workflow Ref Binding (Control-Flow Boundary)

Objetivo: mismo `event_name=push`, mismo `ref=refs/heads/main`, distinta `job_workflow_ref` => STRICT debe rechazar el workflow “no permitido”.

Config del consumer (pin a solo `01-push`):

```bash
cd /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/app
. .venv/bin/activate
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/01-push.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Cómo dispararlo:

- Haz un push a `main` (esto ejecuta `01-push` y `05-alt`).

Resultado esperado:

- `01-push`: `STRICT ok=true`
- `05-alt`: `STRICT ok=false` con `workflow_ref_not_allowed: .../05-alt.yml@refs/heads/main`

### H4: Audience Binding (Un Solo Knob)

Objetivo: misma `job_workflow_ref`, mismo `event`, mismo `ref`… solo cambia `aud`.

Config del consumer (pin a `03-dispatch`, y `ALLOWED_AUDIENCES=ci-oidc-lab`):

```bash
cd /Users/gdeangel/Documents/Projects/SecAudits/Identity_Drift_CICD/app
. .venv/bin/activate
ALLOWED_WORKFLOWS="scumfrog/Identity_Drift_CICD/.github/workflows/03-dispatch.yml@refs/heads/main" \
ALLOWED_AUDIENCES="ci-oidc-lab" \
uvicorn consumer:app --host 0.0.0.0 --port 8081
```

Disparo (dos veces, mismo workflow, distinta audience):

```bash
unset GITHUB_TOKEN GH_TOKEN
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=ci-oidc-lab
gh workflow run -R scumfrog/Identity_Drift_CICD "03-dispatch" -f audience=other-service
```

Resultado esperado:

- `aud=ci-oidc-lab`: `STRICT ok=true`
- `aud=other-service`: `STRICT ok=false` con `aud_not_allowed: ['other-service']`
