import re
import uuid
from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from app.models import AuditEvent


_SECRET_KEY = re.compile(
    r"(password|token|secret|credential|authorization|hash)",
    re.IGNORECASE,
)


def _contains_secret_key(value: object) -> bool:
    if isinstance(value, Mapping):
        return any(
            _SECRET_KEY.search(str(key)) or _contains_secret_key(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_secret_key(item) for item in value)
    return False


class AuditService:
    def __init__(self, db: Session):
        self.db = db

    def record(
        self,
        *,
        actor_id: uuid.UUID | None,
        action: str,
        target_type: str,
        target_id: uuid.UUID | None,
        outcome: str = "SUCCESS",
        metadata: Mapping[str, object] | None = None,
    ) -> AuditEvent:
        if outcome not in {"SUCCESS", "FAILURE"}:
            raise ValueError("Invalid audit outcome.")

        safe_metadata = dict(metadata or {})
        if _contains_secret_key(safe_metadata):
            raise ValueError("Audit metadata contains a prohibited secret field.")

        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            outcome=outcome,
            metadata_=safe_metadata,
        )
        self.db.add(event)
        self.db.flush()
        return event
