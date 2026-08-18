from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path


def project_root(base: str, project_id: uuid.UUID) -> Path:
    root = Path(base) / str(project_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_join(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if root.resolve() not in target.parents and target != root.resolve():
        raise ValueError("Invalid path")
    return target


def file_tree(root: Path) -> dict:
    def walk(path: Path) -> list[dict]:
        items: list[dict] = []
        for entry in sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if entry.name.startswith(".git"):
                continue
            if entry.is_dir():
                items.append({"type": "dir", "name": entry.name, "children": walk(entry)})
            else:
                items.append({"type": "file", "name": entry.name, "size": entry.stat().st_size})
        return items

    return {"name": root.name, "children": walk(root)}


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
