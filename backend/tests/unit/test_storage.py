import os
from pathlib import Path
import subprocess

import pytest

from app.core.storage import ArtifactStorage, UnsafeStoragePath


@pytest.fixture
def storage(tmp_path):
    return ArtifactStorage(tmp_path / "data")


@pytest.mark.parametrize("key", ["../outside", "/absolute", "C:/outside", "evidence/../../outside", "evidence\\outside", "evidence//x", "evidence/NUL.png", "evidence/name.", "unknown/a.png", "evidence"])
def test_invalid_paths_cannot_escape_or_use_windows_devices(storage, key):
    with pytest.raises(UnsafeStoragePath):
        storage.resolve(key)


def test_bounded_atomic_write_and_idempotent_delete(storage):
    key = storage.write(b"sample", category="evidence", suffix=".txt", max_bytes=6)
    assert storage.resolve(key).read_bytes() == b"sample"
    assert not list(storage.root.rglob(".staged-*"))
    with pytest.raises(ValueError):
        storage.write(b"oversized", category="evidence", suffix=".txt", max_bytes=2)
    storage.delete(key)
    storage.delete(key)


def test_failed_publish_cleans_up_staging(storage, monkeypatch):
    def fail_replace(*_args):
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError):
        storage.write(b"sample", category="evidence", suffix=".txt", max_bytes=6)
    assert not list(storage.root.rglob(".staged-*"))
    assert not list(storage.root.rglob("*.txt"))


def test_linked_directory_cannot_reach_outside(storage, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")
    link = storage.root / "evidence"
    junction = False
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name != "nt":
            pytest.skip("Directory links are not permitted on this environment.")
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(outside)],
            capture_output=True, check=False,
        )
        if result.returncode != 0:
            pytest.skip("Windows junction creation is unavailable.")
        junction = True
    try:
        with pytest.raises(UnsafeStoragePath):
            storage.resolve("evidence/keep.txt")
        assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    finally:
        if junction:
            os.rmdir(link)  # Removes the junction itself, never its target.
        else:
            link.unlink()
