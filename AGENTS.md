# StackForge Agent Notes

These notes describe the current deployment-specific architecture and constraints. Read this file before changing preview routing, Docker networking, authentication, or AI file operations.

## Deployment

- StackForge is a self-hosted internal tool running with Docker Compose on a single LAN server.
- Deployment-specific values (server address, checkout path, secrets) live in the untracked
  `.env`. Docs below use `<server-lan-ip>` where the real address appears in `.env`.
- Users enter through Caddy on port `18181` (HTTP). PostgreSQL, the API, frontend, and runner are not published directly.
- The source checkout lives on the server; `PROJECTS_HOST_ROOT` in `.env` must point at
  its `volumes/projects` directory as the Docker daemon sees it.
- Do not commit or print `.env`; `.env.example` contains safe placeholders.

## Built-in preview architecture

The Preview panel is intended to display a project's running container inside an iframe. The complete request path is:

```text
Browser iframe
  -> project UUID hostname on port 18181
  -> Caddy Host-header matcher
  -> stackforge-runner /proxy/<project-uuid>/...
  -> labeled preview container on stackforge_default
```

Preview URLs currently look like:

```text
http://<project-uuid>.<server-lan-ip>.sslip.io:18181/
```

The pieces are:

- `<project-uuid>` uniquely selects the StackForge project and preview container.
- `<server-lan-ip>` is the StackForge server's LAN address.
- `sslip.io` is a public wildcard DNS service. A hostname containing an IPv4 address resolves to that address, so no local wildcard DNS configuration is required.
- `18181` is the host port published by the StackForge Caddy service.

Caddy extracts the UUID from the Host header and rewrites the request to the runner's internal proxy endpoint. The runner validates that the target container has the matching `com.stackforge.preview` ownership label, reads its declared internal port from `stackforge.json`, and proxies the request over the private Compose network.

This hostname-based approach is important. It lets generated apps use root-relative asset and API paths without those requests escaping a `/preview/<uuid>/` path prefix.

### Preview security invariants

- Only the runner mounts the Docker socket.
- Preview containers do not publish host ports.
- Preview containers join only the configured preview/Compose network.
- Preview container operations are scoped by UUID-derived names and ownership labels.
- Preview containers receive resource limits, dropped Linux capabilities, and `no-new-privileges`.
- Do not drop every Linux capability indiscriminately: common rootful images may need `CHOWN`, `SETUID`, or `SETGID` during entrypoint initialization. Prefer unprivileged base images; the runner drops a targeted dangerous subset and applies `no-new-privileges`.
- Platform database, session, and AI secrets must never be passed into preview containers.
- API-to-runner lifecycle calls require `STACKFORGE_RUNNER_TOKEN`.
- The Caddy preview proxy endpoint intentionally does not expose Docker lifecycle operations.

### Relevant settings

- `PREVIEW_BASE_DOMAIN=<server-lan-ip>.sslip.io:18181` is used by the API when storing and returning iframe URLs.
- `PREVIEW_BASE_DOMAIN_HOST=<server-lan-ip>.sslip.io` is passed to Caddy for Host matching.
- `STACKFORGE_PREVIEW_NETWORK=stackforge_default` is normally derived from the Compose project name.

If the server address changes, update both preview-domain settings. For a fully self-hosted DNS setup, replace `sslip.io` with an internal wildcard DNS record such as `*.preview.example.internal` pointing at the StackForge server, then update both settings.

## Preview behavior and verification

- **Build Preview** builds the project image, replaces the project's prior preview container, starts it, refreshes project state, displays its URL, reloads the iframe, and moves the user to the Preview panel.
- A build is successful only after the runner waits briefly, reloads container state, and confirms it remains `running`; startup failures must return bounded container logs.
- **Restart Preview** rebuilds using the current implementation; it is not merely a container restart.
- **Stop Preview** stops the container but preserves project files and image state.
- **Delete Project** requires confirmation and permanently removes the preview container/image, database children and project row, workspace, and filesystem checkpoints.
- The preview URL must be shown as a clickable link with `target="_blank"` in addition to the iframe.

After preview changes, verify all of the following:

1. `docker compose config --quiet`
2. Caddy configuration validation
3. The preview container is on `stackforge_default` and has no published ports
4. `curl` with the preview Host header returns the generated app
5. The full `sslip.io:18181` URL returns HTTP 200 from a LAN client
6. The project record contains the routed preview URL
7. Backend tests pass

## AI change boundary

- The AI endpoint is OpenAI-compatible and configured through LiteLLM environment settings.
- AI output is strict JSON containing validated create/update/delete file operations.
- For compatibility with otherwise valid model responses, a file operation that omits `action` defaults to `update`; unknown action values and unknown fields remain rejected.
- Protected paths such as `.git`, `.stackforge`, `node_modules`, and `.next` cannot be edited by AI operations.
- `stackforge.json` is platform metadata and cannot be changed by AI operations. The runner uses one shared port resolver for build and proxy: declared `port`, then Dockerfile `EXPOSE`/common command patterns, then port `3000`.
- AI-suggested commands are informational and must not be executed automatically.
- A checkpoint is created before AI changes, and failed application restores that checkpoint.

## Source-editing expectations

- Preserve existing user work and runtime volumes.
- Never replace or expose the live `.env`.
- Validate Python compilation, frontend build/type checking, Compose expansion, tests, and health endpoints in proportion to the change.
- Keep project access checks on every files, checkpoints, logs, AI, and preview endpoint; non-admin users may access only projects they own.
