"""Process-lifetime OS lock; heartbeat age never grants ownership."""
import os
from pathlib import Path
from app.core.storage import reject_links


class WorkerAlreadyRunning(RuntimeError):
    pass


class WorkerLock:
    def __init__(self, root: Path):
        self.path = root / 'worker.lock'
        self.handle = None

    def acquire(self):
        reject_links(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open('a+b')
        if self.path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise WorkerAlreadyRunning('Another worker owns this data directory.') from None
        self.handle = handle

    def release(self):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


def lock_is_held(root: Path) -> bool:
    lock = WorkerLock(root)
    try:
        lock.acquire()
    except WorkerAlreadyRunning:
        return True
    finally:
        lock.release()
    return False
