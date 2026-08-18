from __future__ import annotations

import json
import os
import re
import secrets
import time
from pathlib import Path
from uuid import UUID

import docker
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel


app = FastAPI(title="StackForge Runner", version="0.1.0")
client = docker.from_env()
PROJECTS_ROOT = Path(os.environ.get("PROJECTS_ROOT", "/data/projects"))
PROJECTS_HOST_ROOT = Path(os.environ.get("PROJECTS_HOST_ROOT", "/data/projects"))
CONTAINER_PREFIX = "stackforge-preview"
RUNNER_TOKEN = os.environ.get("STACKFORGE_RUNNER_TOKEN", "")
STACKFORGE_LABEL = "com.stackforge.preview"
PREVIEW_NETWORK = os.environ.get("STACKFORGE_PREVIEW_NETWORK", "stackforge_default")


class PreviewBuildRequest(BaseModel):
    project_id: UUID
    port: int = 3001


class PreviewStopRequest(BaseModel):
    project_id: UUID


def project_dir(project_id: UUID) -> Path:
    path = (PROJECTS_ROOT / str(project_id)).resolve()
    if PROJECTS_ROOT.resolve() not in path.parents or not path.is_dir():
        raise HTTPException(status_code=404, detail="Project workspace not found")
    return path


def project_host_dir(project_id: UUID) -> Path:
    return PROJECTS_HOST_ROOT / str(project_id)


def read_stackforge_config(project_id: UUID) -> dict:
    cfg = project_dir(project_id) / "stackforge.json"
    if cfg.exists():
        return json.loads(cfg.read_text(encoding="utf-8"))
    return {"port": 3000, "command": "npm run dev"}


def resolve_app_port(project_id: UUID, cfg: dict) -> int:
    configured = cfg.get("port")
    if configured is not None:
        port = int(configured)
        if 1 <= port <= 65535:
            return port

    dockerfile = project_dir(project_id) / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8", errors="ignore") if dockerfile.exists() else ""
    patterns = (
        r"(?im)^\s*EXPOSE\s+(\d{2,5})\b",
        r"http\.server(?:\s+|[^0-9]+)(\d{2,5})\b",
        r"(?:--port|-p)(?:=|\s+)[\"']?(\d{2,5})\b",
    )
    for source in (str(cfg.get("command", "")), content):
        for pattern in patterns:
            match = re.search(pattern, source)
            if match:
                port = int(match.group(1))
                if 1 <= port <= 65535:
                    return port
    return 3000


def container_name(project_id: UUID) -> str:
    return f"{CONTAINER_PREFIX}-{project_id}"


def existing_container(project_id: UUID):
    try:
        container = client.containers.get(container_name(project_id))
        if container.labels.get(STACKFORGE_LABEL) != str(project_id):
            raise HTTPException(status_code=409, detail="Container name is not owned by StackForge")
        return container
    except docker.errors.NotFound:
        return None


def authenticate_runner(x_stackforge_runner_token: str = Header(default="")) -> None:
    if not RUNNER_TOKEN or not secrets.compare_digest(x_stackforge_runner_token, RUNNER_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid runner credentials")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/preview/build", dependencies=[Depends(authenticate_runner)])
def build_preview(payload: PreviewBuildRequest) -> dict[str, object]:
    cfg = read_stackforge_config(payload.project_id)
    app_port = resolve_app_port(payload.project_id, cfg)
    name = container_name(payload.project_id)

    current = existing_container(payload.project_id)
    if current:
        try:
            current.stop(timeout=5)
        except Exception:
            pass
        try:
            current.remove(force=True)
        except Exception:
            pass

    image_tag = f"stackforge-preview:{payload.project_id}"
    # The Docker SDK reads the build context from the runner container filesystem.
    # The bind-mounted workspace lives at /data/projects inside this container.
    client.images.build(path=str(project_dir(payload.project_id)), tag=image_tag, rm=True)
    container = client.containers.run(
        image_tag,
        name=name,
        detach=True,
        environment={"PORT": str(app_port)},
        restart_policy={"Name": "unless-stopped"},
        labels={STACKFORGE_LABEL: str(payload.project_id)},
        mem_limit="512m",
        nano_cpus=1_000_000_000,
        pids_limit=256,
        cap_drop=["AUDIT_WRITE", "MKNOD", "NET_RAW"],
        security_opt=["no-new-privileges:true"],
        network=PREVIEW_NETWORK,
    )

    logs_path = project_dir(payload.project_id) / ".stackforge" / "logs"
    logs_path.mkdir(parents=True, exist_ok=True)
    time.sleep(2)
    container.reload()
    startup_logs = container.logs(tail=2000).decode("utf-8", errors="ignore")
    (logs_path / "preview.log").write_text(startup_logs, encoding="utf-8")
    if container.status != "running":
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Preview container exited during startup",
                "logs": startup_logs[-4000:],
            },
        )

    return {"container_id": container.id, "port": app_port, "logs_path": str(logs_path / "preview.log")}


@app.post("/preview/stop", dependencies=[Depends(authenticate_runner)])
def stop_preview(payload: PreviewStopRequest) -> dict[str, str]:
    container = existing_container(payload.project_id)
    if not container:
        return {"status": "not-running"}
    container.stop(timeout=5)
    return {"status": "stopped"}


@app.post("/preview/delete", dependencies=[Depends(authenticate_runner)])
def delete_preview(payload: PreviewStopRequest) -> dict[str, str]:
    container = existing_container(payload.project_id)
    if container:
        container.remove(force=True)
    image_tag = f"stackforge-preview:{payload.project_id}"
    try:
        client.images.remove(image=image_tag, force=True)
    except docker.errors.ImageNotFound:
        pass
    return {"status": "deleted"}


@app.api_route(
    "/proxy/{project_id}/{path:path}",
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_preview(project_id: UUID, path: str, request: Request) -> Response:
    """Proxy a Caddy-routed request to a labeled running preview container."""
    container = existing_container(project_id)
    if not container or container.status != "running":
        raise HTTPException(status_code=404, detail="Preview is not running")

    cfg = read_stackforge_config(project_id)
    app_port = resolve_app_port(project_id, cfg)
    upstream = f"http://{container_name(project_id)}:{app_port}/{path}"
    if request.url.query:
        upstream = f"{upstream}?{request.url.query}"

    forwarded_headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "connection", "content-length", "accept-encoding"}
    }
    try:
        upstream_response = requests.request(
            request.method,
            upstream,
            headers=forwarded_headers,
            data=await request.body(),
            timeout=30,
            allow_redirects=False,
        )
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail="Preview application is unavailable") from exc

    response_headers = {
        key: value
        for key, value in upstream_response.headers.items()
        if key.lower() not in {"connection", "content-length", "content-encoding", "transfer-encoding"}
    }
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
