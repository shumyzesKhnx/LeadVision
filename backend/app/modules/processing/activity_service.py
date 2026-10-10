"""Append an event inside its caller's transaction; deduplicate explicit retries."""

import json

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from app.modules.processing.activity_model import Activity

ORIGINS = {"operator", "api", "worker", "import", "n8n"}
FORBIDDEN_KEYS = {"password", "secret", "token", "api_key", "authorization", "credential"}


def _validate_snapshot(value) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        raise ValueError("Activity snapshots must be objects.")

    def check_keys(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str) or any(word in key.lower() for word in FORBIDDEN_KEYS):
                    raise ValueError("Sensitive activity fields are not allowed.")
                check_keys(child)
        elif isinstance(item, list):
            for child in item:
                check_keys(child)

    check_keys(value)
    if len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) > 4000:
        raise ValueError("Activity snapshot is too large.")


def record_activity(
    session: Session,
    *,
    action: str,
    origin: str,
    actor_label: str | None = None,
    agency_id: str | None = None,
    campaign_id: str | None = None,
    lead_id: str | None = None,
    event_key: str | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> Activity:
    if not action.strip() or len(action) > 100 or origin not in ORIGINS:
        raise ValueError("Invalid activity action or origin.")
    if actor_label is not None and len(actor_label) > 200:
        raise ValueError("Actor label is too long.")
    if event_key is not None and (not event_key.strip() or len(event_key) > 200):
        raise ValueError("Invalid event key.")
    _validate_snapshot(old_value)
    _validate_snapshot(new_value)
    values = dict(
        action=action, origin=origin, actor_label=actor_label,
        agency_id=agency_id, campaign_id=campaign_id, lead_id=lead_id,
        event_key=event_key, old_value=old_value, new_value=new_value,
    )
    statement = insert(Activity).values(**values)
    if event_key is not None:
        statement = statement.on_conflict_do_nothing(index_elements=[Activity.event_key])
    result = session.execute(statement.returning(Activity.id)).scalar_one_or_none()
    if result is None:
        return session.execute(select(Activity).where(Activity.event_key == event_key)).scalar_one()
    return session.get(Activity, result)
