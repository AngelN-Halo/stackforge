import uuid

import pytest
from pydantic import ValidationError

from app.schemas import PasswordChange, UserCreate, UserUpdate
from app.users import MIN_PASSWORD_LENGTH, leaves_no_active_admin


ADMIN = uuid.uuid4()
OTHER_ADMIN = uuid.uuid4()
BUILDER = uuid.uuid4()


def test_demoting_the_only_admin_is_refused() -> None:
    users = [(ADMIN, "admin", True), (BUILDER, "builder", True)]
    assert leaves_no_active_admin(users, ADMIN, new_role="builder") is True


def test_deactivating_the_only_admin_is_refused() -> None:
    users = [(ADMIN, "admin", True), (BUILDER, "builder", True)]
    assert leaves_no_active_admin(users, ADMIN, new_is_active=False) is True


def test_demoting_one_of_two_admins_is_allowed() -> None:
    users = [(ADMIN, "admin", True), (OTHER_ADMIN, "admin", True)]
    assert leaves_no_active_admin(users, ADMIN, new_role="builder") is False


def test_a_deactivated_admin_does_not_count_as_cover() -> None:
    users = [(ADMIN, "admin", True), (OTHER_ADMIN, "admin", False)]
    assert leaves_no_active_admin(users, ADMIN, new_role="viewer") is True


def test_promoting_a_builder_is_always_allowed() -> None:
    users = [(ADMIN, "admin", True), (BUILDER, "builder", True)]
    assert leaves_no_active_admin(users, BUILDER, new_role="admin") is False


def test_reactivating_the_last_admin_is_allowed() -> None:
    users = [(ADMIN, "admin", False), (BUILDER, "builder", True)]
    assert leaves_no_active_admin(users, ADMIN, new_is_active=True) is False


def test_unrelated_change_keeps_existing_roles() -> None:
    users = [(ADMIN, "admin", True), (BUILDER, "builder", True)]
    assert leaves_no_active_admin(users, BUILDER, new_is_active=False) is False


def test_short_passwords_are_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="someone@example.com", password="x" * (MIN_PASSWORD_LENGTH - 1))
    with pytest.raises(ValidationError):
        PasswordChange(current_password="anything", new_password="short")


def test_user_create_defaults_to_builder() -> None:
    created = UserCreate(email="someone@example.com", password="x" * MIN_PASSWORD_LENGTH)
    assert created.role == "builder"


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="someone@example.com", password="x" * MIN_PASSWORD_LENGTH, role="superuser")


def test_empty_user_update_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UserUpdate()


def test_user_update_accepts_a_single_field() -> None:
    assert UserUpdate(is_active=False).role is None
    assert UserUpdate(role="viewer").is_active is None
