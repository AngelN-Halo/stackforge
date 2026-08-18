# StackForge Architecture

Orientation for anyone reading this codebase for the first time.
`README.md` covers setup and `AGENTS.md` covers preview-routing constraints in depth —
this file is the map that makes both of those easier to read.

**Start here:** the system is ~1,850 lines. Read three files and you have ~90% of it:
[`proxy/Caddyfile`](proxy/Caddyfile) (routing), [`backend/app/main.py`](backend/app/main.py)
(all business logic), [`runner/app.py`](runner/app.py) (all Docker control).

---

## Services

Six containers. **Only Caddy publishes host ports** (18181 HTTP, 18443 HTTPS);
everything else is reachable only on the private Compose network `stackforge_default`.

| Container | Role | Entry point |
|---|---|---|
| `stackforge-proxy` | Caddy. Single front door, 3 routing rules total. | [`proxy/Caddyfile`](proxy/Caddyfile) |
| `stackforge-web` | Next.js UI. | [`frontend/src/components/Workspace.tsx`](frontend/src/components/Workspace.tsx) |
| `stackforge-api` | FastAPI. Auth, projects, files, AI, checkpoints. | [`backend/app/main.py`](backend/app/main.py) |
| `stackforge-runner` | **The only container with the Docker socket.** Builds and proxies previews. | [`runner/app.py`](runner/app.py) |
| `stackforge-postgres` | Users, projects, checkpoints, preview jobs. | [`backend/migrations/0001_initial.sql`](backend/migrations/0001_initial.sql) |
| `stackforge-redis` | Job queue — **currently unused, see Known gaps.** | — |
| `stackforge-worker` | Queue consumer — **currently a stub, see Known gaps.** | [`worker/app.py`](worker/app.py) |

The single most important structural rule: **the API never touches the Docker socket.**
It reaches the runner over authenticated HTTP (`STACKFORGE_RUNNER_TOKEN`). If you are
tempted to call Docker from the API, that is the invariant you would be breaking.

## Request routing

Caddy makes exactly three decisions, in this order:

1. **Host matches `<uuid>.<PREVIEW_BASE_DOMAIN>`** → rewrite to `/proxy/<uuid>/...`, forward to runner
2. **Path starts with `/api/`** → strip `/api`, forward to the API
3. **Everything else** → forward to the Next.js app

Because of rule 2, browser code must call `/api/...` and never `http://localhost:8000`.
All of it lives in [`frontend/src/lib/api.ts`](frontend/src/lib/api.ts) — use that client.

## Preview: the one genuinely clever part

Everything else here is CRUD. This is where the real design is.

```
Browser iframe
  -> http://<project-uuid>.192.168.1.180.sslip.io:18181/
  -> Caddy Host regex extracts the UUID, rewrites to /proxy/<uuid><uri>
  -> stackforge-runner verifies the com.stackforge.preview ownership label
  -> runner reads the container's declared port from stackforge.json
  -> proxies over stackforge_default to stackforge-preview-<uuid>
```

Two things worth understanding, because neither is obvious:

- **Why `sslip.io`:** it is a public wildcard DNS service that resolves any hostname
  containing an IPv4 address back to that address. So per-project subdomains work with
  zero local DNS setup. To go fully self-hosted, point an internal wildcard record at
  this server and update `PREVIEW_BASE_DOMAIN` + `PREVIEW_BASE_DOMAIN_HOST`.
- **Why hostname-based instead of `/preview/<uuid>/`:** generated apps use root-relative
  paths (`/api/x`, `/logo.png`). Under a path prefix those requests escape the prefix and
  break. Giving each project its own hostname makes root-relative paths work unmodified.

Preview containers publish no host ports, join only the Compose network, get resource
limits, `no-new-privileges`, and a targeted capability drop — and never receive platform
DB/Redis/session/AI secrets. See `AGENTS.md` for the full invariant list before changing
any of it.

## The AI edit loop

`POST /projects/{id}/generate` in `main.py`:

1. Take a filesystem checkpoint (`.stackforge/snapshots`)
2. Ask the LiteLLM-compatible endpoint for **strict JSON** create/update/delete file ops
3. Validate: reject unknown actions/fields, and protected paths (`.git`, `.stackforge`,
   `node_modules`, `.next`, `stackforge.json`)
4. Apply the ops — **on failure, restore the checkpoint**
5. Suggested shell commands are returned as information only and are never executed

## Where things live

```
backend/app/
  main.py       all HTTP routes, grouped by section banner comments
  models.py     SQLAlchemy tables        schemas.py   Pydantic request/response
  workspace.py  file ops + snapshots     security.py  JWT + password hashing
  ai.py         LiteLLM call + JSON      preview.py   preview URL construction
  utils.py      safe_join, file_tree     config.py    env settings
runner/app.py   build / stop / delete / reverse-proxy previews  (has the Docker socket)
templates/      starter projects copied on project creation
volumes/        runtime state — postgres, redis, caddy, projects. Do not edit by hand.
```

`main.py` is one long file by design, but it is divided by `# ---` section banners:
serializers → auth dependencies → bootstrap → lifecycle → auth → settings → projects →
files → AI → checkpoints → preview → export. Jump between banners to navigate it.

## Known gaps

Things that look intentional but are not — worth knowing before you trust them:

- **The Redis worker is a no-op.** `worker/app.py` blocks forever on the
  `stackforge:jobs` list, but *nothing enqueues to it* — there is no `rpush`/`lpush`
  anywhere in the API or runner, and the backend never imports redis. Preview builds are
  synchronous API→runner HTTP calls. The worker and Redis services are currently
  scaffolding for async job handling that was never wired up. Either wire preview builds
  through the queue or drop both services; do not assume builds are already async.
- **No git.** This directory is not a repository, so there is no undo. Take copies before
  invasive changes.
- **`ARCHIVE-stackforge-update-2026-06/`** (one level up) is a stale partial fork that
  nothing runs from. Do not read it to understand the system.

## Verifying changes

Per `AGENTS.md`, after preview/routing changes: `docker compose config --quiet`, validate
the Caddy config, confirm the preview container is on `stackforge_default` with no
published ports, `curl` with the preview Host header, load the full `sslip.io:18181` URL
from a LAN client, check the project row holds the routed URL, and run the backend tests.
