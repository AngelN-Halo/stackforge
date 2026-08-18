# StackForge

StackForge is a self-hosted, Docker-based AI app builder for a small trusted team.

## What it does

- Login with seeded admin credentials
- Create projects from starter templates
- Generate and edit code through chat
- Save files into an isolated project workspace
- Build, stop, and restart preview containers
- Store checkpoints before AI edits and restore prior versions

## Start

1. Copy `.env.example` to `.env`
2. Fill in `STACKFORGE_ADMIN_EMAIL`, `STACKFORGE_ADMIN_PASSWORD`, `DATABASE_URL`, and AI settings
3. Run `docker compose up -d`
4. Open the frontend on `http://localhost:3000` or the LAN proxy on `http://<host-ip>:18181`

If your checkout lives somewhere other than this workspace path, update `PROJECTS_HOST_ROOT` in `.env` so the runner can bind mount project files correctly.

The browser app talks to the API through `/api` on the proxy, so do not point frontend code at `http://localhost:8000`.

## Admin user

The first admin user is seeded from environment variables:

- `STACKFORGE_ADMIN_EMAIL`
- `STACKFORGE_ADMIN_PASSWORD`

Default local login:

- Email: `admin@stackforge.local`
- Password: `changeme123`

## AI settings

- `LITELLM_BASE_URL` should point at a LiteLLM-compatible endpoint
- `LITELLM_API_KEY` is passed to that endpoint
- `DEFAULT_MODEL` controls the model used for generation

## Preview flow

1. Create a project
2. StackForge copies the selected starter template into `PROJECTS_ROOT/<project-id>`
3. The runner builds a Docker image from the project folder
4. A preview container starts on an internal port
5. The UI shows logs and preview state

Preview URLs use `*.localhost` by default, so they resolve without extra DNS setup.

## Security notes

- Intended for trusted internal use only
- Do not expose Docker control to the web app
- Keep preview containers away from sensitive host paths
- Avoid placing secrets inside project workspaces

## Backups

- Back up PostgreSQL regularly
- Back up `PROJECTS_ROOT`
- Preserve `.stackforge/snapshots` if you want checkpoint history

## Troubleshooting

- If the API cannot reach LiteLLM, verify `LITELLM_BASE_URL`
- If previews fail, inspect runner logs and the generated project Dockerfile
- If login fails, confirm the seeded admin credentials
- If a page is still trying to call `http://localhost:8000`, rebuild the frontend container and make sure the page uses the shared API client
