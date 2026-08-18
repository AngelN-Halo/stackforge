from __future__ import annotations

import json
import uuid
from pathlib import Path
import shutil

from app.utils import copy_tree, project_root, safe_join, write_json


class WorkspaceManager:
    def __init__(self, base_root: str):
        self.base_root = base_root

    def root(self, project_id: uuid.UUID) -> Path:
        return project_root(self.base_root, project_id)

    def read_file(self, project_id: uuid.UUID, path: str) -> str:
        target = safe_join(self.root(project_id), path)
        return target.read_text(encoding="utf-8")

    def write_file(self, project_id: uuid.UUID, path: str, content: str) -> Path:
        self._validate_edit_path(path)
        target = safe_join(self.root(project_id), path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def delete_file(self, project_id: uuid.UUID, path: str) -> None:
        self._validate_edit_path(path)
        target = safe_join(self.root(project_id), path)
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()

    def rename(self, project_id: uuid.UUID, old_path: str, new_path: str) -> None:
        self._validate_edit_path(old_path)
        self._validate_edit_path(new_path)
        old_target = safe_join(self.root(project_id), old_path)
        new_target = safe_join(self.root(project_id), new_path)
        new_target.parent.mkdir(parents=True, exist_ok=True)
        old_target.rename(new_target)

    @staticmethod
    def _validate_edit_path(path: str) -> None:
        first = Path(path).parts[0] if Path(path).parts else ""
        if first in {".git", ".stackforge", "stackforge.json", "node_modules", ".next"}:
            raise ValueError(f"Editing {first} is not allowed")
        if "\x00" in path or Path(path).is_absolute():
            raise ValueError("Invalid project-relative path")

    def apply_ai_changes(self, project_id: uuid.UUID, changes: list) -> None:
        for change in changes:
            if change.action in {"create", "update"}:
                self.write_file(project_id, change.path, change.content or "")
            else:
                self.delete_file(project_id, change.path)

    def delete_project(self, project_id: uuid.UUID) -> None:
        project = Path(self.base_root) / str(project_id)
        snapshots = Path(self.base_root) / ".stackforge" / "snapshots" / str(project_id)
        for target in (project, snapshots):
            resolved = target.resolve()
            base = Path(self.base_root).resolve()
            if base not in resolved.parents:
                raise ValueError("Refusing to delete path outside projects root")
            if resolved.exists():
                shutil.rmtree(resolved)

    def snapshot(self, project_id: uuid.UUID, version: int, label: str) -> Path:
        project = self.root(project_id)
        snapshot_dir = Path(self.base_root) / ".stackforge" / "snapshots" / str(project_id) / f"v{version}"
        snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
        shutil.copytree(project, snapshot_dir, ignore=shutil.ignore_patterns(".stackforge"))
        write_json(snapshot_dir / "meta.json", {"version": version, "label": label})
        return snapshot_dir

    def restore(self, project_id: uuid.UUID, snapshot_path: str) -> None:
        project = self.root(project_id)
        snapshot = Path(snapshot_path)
        copy_tree(snapshot, project)

    def tree(self, project_id: uuid.UUID) -> dict:
        from app.utils import file_tree

        return file_tree(self.root(project_id))

    def load_context_files(self, project_id: uuid.UUID, file_paths: list[str]) -> dict[str, str]:
        context: dict[str, str] = {}
        for file_path in file_paths[:10]:
            target = safe_join(self.root(project_id), file_path)
            if target.exists() and target.is_file():
                context[file_path] = target.read_text(encoding="utf-8")[:20000]
        return context
