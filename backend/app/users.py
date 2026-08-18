from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID


MIN_PASSWORD_LENGTH = 12
ASSIGNABLE_ROLES = ("admin", "builder", "viewer")


def leaves_no_active_admin(
    users: Iterable[tuple[UUID, str, bool]],
    target_id: UUID,
    new_role: str | None = None,
    new_is_active: bool | None = None,
) -> bool:
    """Would applying this change to target_id leave the platform with no active admin?

    `users` is every user as they exist now, as (id, role, is_active). Kept free of
    database and request types so the rule can be tested directly: locking every
    admin out is the one user-administration mistake that cannot be undone through
    the UI, and it takes shell access on the server to repair.
    """
    remaining = 0
    for user_id, role, is_active in users:
        if user_id == target_id:
            role = new_role if new_role is not None else role
            is_active = new_is_active if new_is_active is not None else is_active
        if role == "admin" and is_active:
            remaining += 1
    return remaining == 0
