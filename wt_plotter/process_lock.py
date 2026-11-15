"""进程间互斥锁。"""

from contextlib import contextmanager
import msvcrt
from pathlib import Path


class LockHeld(Exception):
    """锁文件已被其它进程占用。"""


@contextmanager
def hold_lock(path: Path):
    """持有锁文件直到退出代码块；进程异常退出时系统会自动释放。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise LockHeld(str(path)) from error
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
