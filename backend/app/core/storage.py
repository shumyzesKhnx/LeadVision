"""Write opaque artifact keys under one controlled directory."""

import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from uuid import uuid4


class UnsafeStoragePath(ValueError):
    pass


def reject_links(path: Path) -> None:
    """Reject symlinks and Windows junction/reparse points, including parents."""
    for candidate in [path, *path.parents]:
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise UnsafeStoragePath("Linked storage paths are not allowed.")


class ArtifactStorage:
    ALLOWED_FOLDERS = {"evidence", "knowledge", "diagnostics", "trash"}

    def __init__(self, root: Path):
        reject_links(root)
        root.mkdir(parents=True, exist_ok=True)
        self.root = root.resolve()

    def resolve(self, key: str) -> Path:
        # Keys are POSIX-like identifiers, never client-selected filesystem paths.
        if not key or "\\" in key or ":" in key or "\x00" in key:
            raise UnsafeStoragePath("Invalid artifact key.")
        parsed = PurePosixPath(key)
        if parsed.is_absolute() or any(part in {".", ".."} for part in key.split("/")):
            raise UnsafeStoragePath("Invalid artifact key.")
        if any(not re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in key.split("/")):
            raise UnsafeStoragePath("Invalid artifact key.")
        reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
        if any(part.endswith(".") or part.split(".")[0].upper() in reserved for part in parsed.parts):
            raise UnsafeStoragePath("Invalid artifact name.")
        if len(parsed.parts) < 2 or parsed.parts[0] not in self.ALLOWED_FOLDERS:
            raise UnsafeStoragePath("Unknown artifact category.")
        target = self.root.joinpath(*parsed.parts)
        reject_links(self.root)
        reject_links(target)
        if not target.resolve().is_relative_to(self.root):
            raise UnsafeStoragePath("Artifact is outside the data directory.")
        return target

    def write(self, content: bytes, *, category: str, suffix: str, max_bytes: int) -> str:
        """Call after type/content validation; stage and atomically publish bytes."""
        if category not in self.ALLOWED_FOLDERS or not re.fullmatch(r"\.[a-z0-9]+", suffix):
            raise UnsafeStoragePath("Invalid artifact category or suffix.")
        if max_bytes < 0 or len(content) > max_bytes:
            raise ValueError("Artifact exceeds its byte limit.")
        key = f"{category}/{uuid4().hex}{suffix}"
        target = self.resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.resolve(key)
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".staged-", delete=False) as file:
                temporary = file.name
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            self.resolve(key)
            os.replace(temporary, target)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        return key

    def delete(self, key: str) -> None:
        self.resolve(key).unlink(missing_ok=True)
