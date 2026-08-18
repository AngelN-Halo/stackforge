from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    email: str
    role: str
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: str
    password: str


class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    template: str = "nextjs-app"


class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: str
    owner_id: UUID
    status: str
    generated_file_tree: dict[str, Any]
    current_version: int
    preview_url: str | None
    deployment_state: str
    created_at: datetime
    updated_at: datetime


class FilePayload(BaseModel):
    path: str
    content: str


class RenamePayload(BaseModel):
    old_path: str
    new_path: str


class DeletePayload(BaseModel):
    path: str


class AIRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    file_context: list[str] = Field(default_factory=list, max_length=10)


class AIFileChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1, max_length=500)
    content: str | None = Field(default=None, max_length=500_000)
    # Models occasionally omit action for ordinary file writes. Treat those as
    # updates; the workspace write path safely creates the file when absent.
    action: Literal["create", "update", "delete"] = "update"

    @model_validator(mode="after")
    def validate_content(self) -> "AIFileChange":
        if self.action in {"create", "update"} and self.content is None:
            raise ValueError("content is required for create and update operations")
        if self.action == "delete" and self.content not in {None, ""}:
            raise ValueError("delete operations cannot contain file content")
        return self


class AIResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assistant_explanation: str
    files: list[AIFileChange] = Field(max_length=100)
    commands: list[str] = Field(default_factory=list, max_length=20)
    notes: list[str] = Field(default_factory=list, max_length=50)


class CheckpointOut(BaseModel):
    id: UUID
    project_id: UUID
    version: int
    label: str
    snapshot_path: str
    created_by_id: UUID
    created_at: datetime


class PreviewActionRequest(BaseModel):
    port: int | None = None


class PreviewJobOut(BaseModel):
    id: UUID
    project_id: UUID
    action: str
    state: str
    container_id: str | None
    port: int | None
    logs_path: str | None
    error: str | None
    created_at: datetime


class SettingsOut(BaseModel):
    litellm_base_url: str
    default_model: str
    preview_base_domain: str
    max_concurrent_previews: int
    max_context_size: int
