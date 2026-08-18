from pathlib import Path
import uuid

import pytest

from app.preview import preview_domain
from app.schemas import AIResponse
from app.utils import safe_join


def test_safe_join_blocks_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        safe_join(tmp_path, "../../etc/passwd")


def test_preview_domain_uses_project_subdomain() -> None:
    url = preview_domain("192.0.2.10.sslip.io:18181", uuid.uuid4(), 3001)
    assert url.startswith("http://")
    assert ".192.0.2.10.sslip.io:18181" in url
    assert not url.endswith(":3001")


def test_ai_file_write_defaults_to_update() -> None:
    response = AIResponse(
        assistant_explanation="Updated the page",
        files=[{"path": "index.html", "content": "<h1>Hello</h1>"}],
    )
    assert response.files[0].action == "update"
