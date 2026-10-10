"""Stable hashes for snapshots, cache inputs and artifact contents."""

import hashlib
import json
from typing import Any


def content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def snapshot_hash(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    return content_hash(encoded)
