from pathlib import Path
from stillhem.auth import (
    hash_password,
    verify_password,
    set_password,
    check_password,
    is_password_set,
    create_session_token,
    validate_session_token,
)


def test_hash_and_verify_correct_password() -> None:
    hashed = hash_password("correcthorsebatterystaple")
    assert verify_password("correcthorsebatterystaple", hashed) is True


def test_hash_and_verify_wrong_password() -> None:
    hashed = hash_password("correcthorsebatterystaple")
    assert verify_password("wrongpassword", hashed) is False


def test_set_and_check_password(db_path: Path) -> None:
    set_password("mypassword", db_path)
    assert check_password("mypassword", db_path) is True
    assert check_password("wrongpassword", db_path) is False


def test_is_password_set_false_initially(db_path: Path) -> None:
    assert is_password_set(db_path) is False


def test_is_password_set_true_after_set(db_path: Path) -> None:
    set_password("secret", db_path)
    assert is_password_set(db_path) is True


def test_session_token_validates(db_path: Path) -> None:
    token = create_session_token(db_path)
    assert validate_session_token(token, db_path) is True


def test_wrong_session_token_rejected(db_path: Path) -> None:
    create_session_token(db_path)
    assert validate_session_token("not-the-real-token", db_path) is False


def test_new_token_invalidates_old(db_path: Path) -> None:
    old_token = create_session_token(db_path)
    create_session_token(db_path)
    assert validate_session_token(old_token, db_path) is False
