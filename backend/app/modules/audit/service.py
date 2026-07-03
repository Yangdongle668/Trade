import uuid

from sqlalchemy.orm import Session

from app.modules.audit.models import Event


def record(
    db: Session,
    tenant_id: uuid.UUID,
    entity_type: str,
    entity_id: uuid.UUID,
    event: str,
    payload: dict | None = None,
) -> None:
    db.add(Event(tenant_id=tenant_id, entity_type=entity_type, entity_id=entity_id,
                 event=event, payload=payload or {}))
