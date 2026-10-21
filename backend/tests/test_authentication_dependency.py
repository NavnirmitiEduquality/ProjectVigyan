from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.dependencies import get_current_user
from app.models import AuthSession, User


@pytest.fixture
def auth_context():
    token = "test-session-token"
    user = Mock(spec=User)
    user.id = uuid4()
    user.status = "ACTIVE"

    session = Mock(spec=AuthSession)
    session.user_id = user.id
    session.revoked_at = None
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    session.last_activity_at = datetime.now(timezone.utc) - timedelta(minutes=2)

    db = Mock()
    query = db.query.return_value
    query.filter.return_value.first.side_effect = [session, user]

    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer",
        credentials=token,
    )

    return token, user, session, db, credentials


def test_unknown_token_is_rejected(auth_context):
    _, _, _, db, credentials = auth_context
    db.query.return_value.filter.return_value.first.side_effect = [None]

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=credentials, db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid or expired session."
    db.commit.assert_not_called()


def test_revoked_session_is_rejected(auth_context):
    _, _, session, db, credentials = auth_context
    session.revoked_at = datetime.now(timezone.utc)

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=credentials, db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Session has been revoked."
    db.commit.assert_not_called()


def test_expired_session_is_rejected(auth_context):
    _, _, session, db, credentials = auth_context
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=credentials, db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Session has expired due to inactivity."
    db.commit.assert_not_called()


def test_inactive_user_is_rejected(auth_context):
    _, user, _, db, credentials = auth_context
    user.status = "INACTIVE"

    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=credentials, db=db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "User account is not active."
    db.commit.assert_not_called()


def test_active_session_refreshes_inactivity_timeout(auth_context):
    token, user, session, db, credentials = auth_context

    with patch("app.dependencies.datetime") as mocked_datetime:
        now = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)
        mocked_datetime.now.return_value = now
        mocked_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        result = get_current_user(credentials=credentials, db=db)

    assert result is user
    assert session.last_activity_at == now
    assert session.expires_at == now + timedelta(minutes=30)
    db.flush.assert_called_once_with()
    db.commit.assert_not_called()
    db.rollback.assert_not_called()
    db.query.assert_any_call(AuthSession)
