from __future__ import annotations

import uuid


def preview_domain(base_domain: str, project_id: uuid.UUID, port: int) -> str:
    """Return the Caddy-routed preview URL.

    ``port`` is retained for API compatibility but previews no longer expose an
    individual host port. PREVIEW_BASE_DOMAIN may include Caddy's public port.
    """
    return f"http://{project_id}.{base_domain}"
