"""Keep storage times in UTC; convert only when displaying them."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def to_karachi(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A stored timestamp must include its timezone.")
    return parsed.astimezone(ZoneInfo("Asia/Karachi")).isoformat()
