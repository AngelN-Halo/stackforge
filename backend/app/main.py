from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import generate_change_plan
from app.config import settings
from app.db import async_session, engine, get_session
from app.models import Base, Checkpoint, PreviewJob, PreviewState, Project, ProjectStatus, Role, User
from app.preview import preview_domain
from app.schemas import (
    AIRequest,
    AIResponse,
    CheckpointOut,
    DeletePayload,
    FilePayload,
    LoginRequest,
    PasswordChange,
    PreviewActionRequest,
    PreviewJobOut,
    ProjectCreate,
    ProjectOut,
    RenamePayload,
    SettingsOut,
    TokenResponse,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.users import leaves_no_active_admin
from app.utils import file_tree, safe_join
from app.workspace import WorkspaceManager


app = FastAPI(title="StackForge API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

workspace = WorkspaceManager(settings.projects_root)


# --------------------------------------------------------------------------
# Serializers
# --------------------------------------------------------------------------

def _project_to_out(project: Project) -> ProjectOut:
    return ProjectOut.model_validate(project, from_attributes=True)


def _user_to_out(user: User) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


def _preview_to_out(job: PreviewJob) -> PreviewJobOut:
    return PreviewJobOut.model_validate(job, from_attributes=True)


# --------------------------------------------------------------------------
# Auth / access-control dependencies
# get_current_user reads the session cookie; require_project_access is the
# per-project ownership gate that every project-scoped route below depends on.
# --------------------------------------------------------------------------

async def get_current_user(
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(default=None),
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(access_token)
        user_id = payload["sub"]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid session") from exc

    user = await session.get(User, uuid.UUID(user_id))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Inactive user")
    return user


def require_role(user: User, roles: set[Role]) -> None:
    if user.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient permissions")


async def require_project_access(
    project_id: uuid.UUID,
    session: AsyncSession,
    user: User,
    write: bool = False,
) -> Project:
    if write:
        require_role(user, {Role.admin, Role.builder})
    project = await session.get(Project, project_id)
    if not project or (user.role != Role.admin and project.owner_id != user.id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# --------------------------------------------------------------------------
# Bootstrap: admin seeding + template copy
# --------------------------------------------------------------------------

async def ensure_admin_user(session: AsyncSession) -> None:
    existing = await session.scalar(select(User).where(User.email == settings.stackforge_admin_email))
    if existing:
        existing.role = Role.admin
        existing.is_active = True
        await session.commit()
        return

    legacy_admin = await session.scalar(select(User).where(User.role == Role.admin))
    if legacy_admin:
        legacy_admin.email = settings.stackforge_admin_email
        legacy_admin.role = Role.admin
        legacy_admin.is_active = True
        await session.commit()
        return
    admin = User(
        email=settings.stackforge_admin_email,
        password_hash=hash_password(settings.stackforge_admin_password),
        role=Role.admin,
    )
    session.add(admin)
    await session.commit()


async def seed_template(project_id: uuid.UUID, template: str) -> dict:
    template_root = Path(settings.stackforge_templates_root) / template
    root = Path(settings.projects_root) / str(project_id)
    if root.exists():
        shutil.rmtree(root)
    shutil.copytree(template_root, root)
    return file_tree(root)


# --------------------------------------------------------------------------
# Lifecycle + health
# --------------------------------------------------------------------------

@app.on_event("startup")
async def startup() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        await ensure_admin_user(session)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# --------------------------------------------------------------------------
# Routes: auth
# --------------------------------------------------------------------------

@app.post("/auth/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, session: AsyncSession = Depends(get_session)) -> TokenResponse:
    user = await session.scalar(select(User).where(User.email == payload.email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # get_current_user also rejects inactive users, but without this a deactivated
    # account still gets a 200 and a cookie here before failing on every next call.
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is deactivated")

    token = create_access_token(str(user.id), user.role.value)
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.jwt_expire_minutes * 60,
    )
    return TokenResponse(access_token=token)


@app.post("/auth/logout")
async def logout(response: Response) -> dict[str, str]:
    response.delete_cookie("access_token")
    return {"status": "ok"}


@app.get("/auth/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_to_out(user)


@app.post("/auth/change-password")
async def change_password(
    payload: PasswordChange,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    """Any authenticated user changes their own password. Admins cannot set another
    user's password: there is no reset flow, so a forgotten password is recovered by
    creating a new account or updating the hash on the server."""
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    if verify_password(payload.new_password, user.password_hash):
        raise HTTPException(status_code=400, detail="New password must differ from the current one")
    user.password_hash = hash_password(payload.new_password)
    await session.commit()
    return {"status": "updated"}


# --------------------------------------------------------------------------
# Routes: settings (read-only view of env config)
# --------------------------------------------------------------------------

@app.get("/settings", response_model=SettingsOut)
async def get_settings(user: User = Depends(get_current_user)) -> SettingsOut:
    require_role(user, {Role.admin})
    return SettingsOut(
        litellm_base_url=settings.litellm_base_url,
        default_model=settings.default_model,
        preview_base_domain=settings.preview_base_domain,
        max_concurrent_previews=settings.max_concurrent_previews,
        max_context_size=settings.max_context_size,
    )


# --------------------------------------------------------------------------
# Routes: users (admin only)
# Deactivating is the supported way to revoke access: projects reference their
# owner, so deleting a user would orphan or cascade their work. There is
# deliberately no endpoint for an admin to set another user's password.
# --------------------------------------------------------------------------


@app.get("/users", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)
) -> list[UserOut]:
    require_role(user, {Role.admin})
    rows = await session.scalars(select(User).order_by(User.created_at))
    return [_user_to_out(row) for row in rows]


@app.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UserOut:
    require_role(user, {Role.admin})
    # Stored as entered: login compares the address exactly, so normalising case
    # here would lock out anyone who signs in the way they were invited.
    email = payload.email.strip()
    if await session.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="A user with that email already exists")

    created = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=Role(payload.role),
    )
    session.add(created)
    await session.commit()
    await session.refresh(created)
    return _user_to_out(created)


@app.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> UserOut:
    require_role(user, {Role.admin})
    target = await session.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    everyone = [(row.id, row.role.value, row.is_active) for row in await session.scalars(select(User))]
    if leaves_no_active_admin(everyone, target.id, payload.role, payload.is_active):
        raise HTTPException(
            status_code=409,
            detail="Refusing this change: it would leave no active admin, which cannot be undone from the UI",
        )

    if payload.role is not None:
        target.role = Role(payload.role)
    if payload.is_active is not None:
        target.is_active = payload.is_active
    await session.commit()
    await session.refresh(target)
    return _user_to_out(target)


# --------------------------------------------------------------------------
# Routes: projects (CRUD)
# --------------------------------------------------------------------------

@app.get("/projects", response_model=list[ProjectOut])
async def list_projects(session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> list[ProjectOut]:
    query = select(Project)
    if user.role != Role.admin:
        query = query.where(Project.owner_id == user.id)
    result = await session.scalars(query.order_by(Project.updated_at.desc()))
    return [_project_to_out(project) for project in result.all()]


@app.post("/projects", response_model=ProjectOut)
async def create_project(
    payload: ProjectCreate,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ProjectOut:
    require_role(user, {Role.admin, Role.builder})
    project = Project(name=payload.name, description=payload.description, owner_id=user.id, status=ProjectStatus.draft)
    session.add(project)
    await session.flush()
    tree = await seed_template(project.id, payload.template)
    project.generated_file_tree = tree
    project.status = ProjectStatus.generated
    project.preview_url = preview_domain(settings.preview_base_domain, project.id, 3001)
    await session.commit()
    await session.refresh(project)
    return _project_to_out(project)


@app.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> ProjectOut:
    project = await require_project_access(project_id, session, user)
    return _project_to_out(project)


@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    project = await require_project_access(project_id, session, user, write=True)
    try:
        await _runner_request("/preview/delete", {"project_id": str(project_id)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail="Could not remove the project preview") from exc

    await session.execute(delete(PreviewJob).where(PreviewJob.project_id == project_id))
    await session.execute(delete(Checkpoint).where(Checkpoint.project_id == project_id))
    await session.delete(project)
    await session.commit()
    workspace.delete_project(project_id)
    return {"status": "deleted"}


# --------------------------------------------------------------------------
# Routes: project files
# All paths go through utils.safe_join; protected paths (.git, .stackforge,
# node_modules, .next) are rejected in workspace/AI layers.
# --------------------------------------------------------------------------

@app.get("/projects/{project_id}/files/tree")
async def project_tree(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict:
    await require_project_access(project_id, session, user)
    return workspace.tree(project_id)


@app.get("/projects/{project_id}/files")
async def read_file(project_id: uuid.UUID, path: str, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user)
    return {"path": path, "content": workspace.read_file(project_id, path)}


@app.post("/projects/{project_id}/files")
async def save_file(project_id: uuid.UUID, payload: FilePayload, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user, write=True)
    workspace.write_file(project_id, payload.path, payload.content)
    return {"status": "saved"}


@app.post("/projects/{project_id}/files/rename")
async def rename_file(project_id: uuid.UUID, payload: RenamePayload, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user, write=True)
    workspace.rename(project_id, payload.old_path, payload.new_path)
    return {"status": "renamed"}


@app.post("/projects/{project_id}/files/delete")
async def delete_file(project_id: uuid.UUID, payload: DeletePayload, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user, write=True)
    workspace.delete_file(project_id, payload.path)
    return {"status": "deleted"}


# --------------------------------------------------------------------------
# Routes: AI code generation
# Takes a checkpoint first, applies strict-JSON file ops from the model,
# and restores the checkpoint if application fails.
# --------------------------------------------------------------------------

@app.post("/projects/{project_id}/generate", response_model=AIResponse)
async def generate(
    project_id: uuid.UUID,
    payload: AIRequest,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> AIResponse:
    project = await require_project_access(project_id, session, user, write=True)

    current_tree = workspace.tree(project_id)
    context_files = workspace.load_context_files(project_id, payload.file_context)

    checkpoint = workspace.snapshot(project_id, project.current_version + 1, f"Before AI edit: {payload.message[:64]}")
    session.add(
        Checkpoint(
            project_id=project.id,
            version=project.current_version + 1,
            label=f"Before AI edit: {payload.message[:64]}",
            snapshot_path=str(checkpoint),
            created_by_id=user.id,
        )
    )
    await session.flush()

    response = await generate_change_plan(project.description, current_tree, context_files, payload.message)

    try:
        workspace.apply_ai_changes(project_id, response.files)
    except Exception:
        workspace.restore(project_id, str(checkpoint))
        await session.rollback()
        raise

    project.current_version += 1
    project.generated_file_tree = workspace.tree(project_id)
    project.status = ProjectStatus.generated
    await session.commit()
    return response


# --------------------------------------------------------------------------
# Routes: checkpoints (restore prior versions)
# --------------------------------------------------------------------------

@app.get("/projects/{project_id}/checkpoints", response_model=list[CheckpointOut])
async def list_checkpoints(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> list[CheckpointOut]:
    await require_project_access(project_id, session, user)
    result = await session.scalars(select(Checkpoint).where(Checkpoint.project_id == project_id).order_by(Checkpoint.created_at.desc()))
    return [CheckpointOut.model_validate(item, from_attributes=True) for item in result.all()]


@app.post("/projects/{project_id}/checkpoints/{checkpoint_id}/restore")
async def restore_checkpoint(
    project_id: uuid.UUID,
    checkpoint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict[str, str]:
    await require_project_access(project_id, session, user, write=True)
    checkpoint = await session.get(Checkpoint, checkpoint_id)
    if not checkpoint or checkpoint.project_id != project_id:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    project = await session.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    workspace.restore(project_id, checkpoint.snapshot_path)
    project.current_version = checkpoint.version
    project.generated_file_tree = workspace.tree(project_id)
    await session.commit()
    return {"status": "restored"}


# --------------------------------------------------------------------------
# Routes: preview lifecycle (delegated to stackforge-runner)
# The API never touches the Docker socket. Every build/start/stop/delete is a
# token-authenticated HTTP call to the runner, which owns the socket.
# These calls are synchronous; there is no background job queue.
# See ARCHITECTURE.md for the full browser -> Caddy -> runner request path.
# --------------------------------------------------------------------------

async def _runner_request(path: str, payload: dict) -> dict:
    import httpx

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{settings.stackforge_runner_url.rstrip('/')}{path}",
            json=payload,
            headers={"X-StackForge-Runner-Token": settings.stackforge_runner_token},
        )
        response.raise_for_status()
        return response.json()


@app.post("/projects/{project_id}/preview/build", response_model=PreviewJobOut)
async def build_preview(project_id: uuid.UUID, payload: PreviewActionRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> PreviewJobOut:
    project = await require_project_access(project_id, session, user, write=True)
    port = payload.port or 3001
    runner_result = await _runner_request("/preview/build", {"project_id": str(project_id), "port": port})
    job = PreviewJob(
        project_id=project_id,
        action="build",
        state=PreviewState.running,
        container_id=runner_result.get("container_id"),
        port=runner_result.get("port", port),
        logs_path=runner_result.get("logs_path"),
    )
    project.preview_url = preview_domain(settings.preview_base_domain, project.id, job.port or port)
    project.deployment_state = "running"
    project.status = ProjectStatus.previewing
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return _preview_to_out(job)


@app.post("/projects/{project_id}/preview/start", response_model=PreviewJobOut)
async def start_preview(project_id: uuid.UUID, payload: PreviewActionRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> PreviewJobOut:
    return await build_preview(project_id, payload, session, user)


@app.post("/projects/{project_id}/preview/stop")
async def stop_preview(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user, write=True)
    await _runner_request("/preview/stop", {"project_id": str(project_id)})
    project = await session.get(Project, project_id)
    if project:
        project.deployment_state = "stopped"
        project.status = ProjectStatus.generated
        await session.commit()
    return {"status": "stopped"}


@app.post("/projects/{project_id}/preview/restart", response_model=PreviewJobOut)
async def restart_preview(project_id: uuid.UUID, payload: PreviewActionRequest, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> PreviewJobOut:
    await require_project_access(project_id, session, user, write=True)
    await _runner_request("/preview/stop", {"project_id": str(project_id)})
    return await build_preview(project_id, payload, session, user)


@app.get("/projects/{project_id}/preview/status")
async def preview_status(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, object]:
    project = await require_project_access(project_id, session, user)
    job = await session.scalar(select(PreviewJob).where(PreviewJob.project_id == project_id).order_by(PreviewJob.created_at.desc()))
    return {
        "project_id": str(project_id),
        "deployment_state": project.deployment_state,
        "preview_url": project.preview_url,
        "job": _preview_to_out(job) if job else None,
    }


@app.get("/projects/{project_id}/preview/logs")
async def preview_logs(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict[str, str]:
    await require_project_access(project_id, session, user)
    logs = Path(settings.projects_root) / str(project_id) / ".stackforge" / "logs" / "preview.log"
    if not logs.exists():
        return {"logs": ""}
    return {"logs": logs.read_text(encoding="utf-8")[-20000:]}


# --------------------------------------------------------------------------
# Routes: export / raw filesystem
# --------------------------------------------------------------------------

@app.get("/projects/{project_id}/download-tree")
async def download_tree(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict:
    await require_project_access(project_id, session, user)
    return workspace.tree(project_id)


@app.get("/projects/{project_id}/filesystem")
async def filesystem_snapshot(project_id: uuid.UUID, session: AsyncSession = Depends(get_session), user: User = Depends(get_current_user)) -> dict:
    await require_project_access(project_id, session, user)
    return file_tree(workspace.root(project_id))
