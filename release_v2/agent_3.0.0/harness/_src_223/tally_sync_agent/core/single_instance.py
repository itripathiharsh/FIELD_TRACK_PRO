"""
Windows named-mutex single-instance guard for the daemon.

Why this is needed (not just belt-and-suspenders): a PyInstaller --onefile build on
Windows runs as a bootloader process that extracts itself to a temp folder and then
spawns a SEPARATE CHILD PROCESS to actually run the code. Windows Task Scheduler's own
"do not start a new instance" setting only tracks the PID it directly launched (the
bootloader) - it has no visibility into that child. If the bootloader exits (normal
onefile behavior) while its child keeps running the daemon loop, Task Scheduler
considers the task "finished" and is free to launch it again, producing a second,
independent child process running the same sync loop concurrently with the first.

A named Windows mutex is a kernel object identified by name and visible machine-wide
to any process, regardless of which bootloader/child spawned it - so it closes this
gap at the level that actually matters (the real daemon process), not at the level
Task Scheduler (mis)tracks.
"""
import ctypes
from ctypes import wintypes
from typing import Optional

from tally_sync_agent.core.logger import logger

ERROR_ALREADY_EXISTS = 183
DEFAULT_MUTEX_NAME = "Global\\FieldTrackTallyAgent_SingleInstance"


def _kernel32():
    # ctypes.windll.kernel32 does NOT track GetLastError() per call unless the DLL
    # handle itself is opened with use_last_error=True - without this,
    # ctypes.get_last_error() can return stale/incorrect values and ERROR_ALREADY_EXISTS
    # is never detected, silently defeating the whole single-instance check.
    dll = ctypes.WinDLL("kernel32", use_last_error=True)
    # Without explicit argtypes/restype, ctypes defaults CreateMutexW's return value to
    # a 32-bit c_int, truncating the real pointer-sized HANDLE on 64-bit Windows. Kernel
    # handles happen to be small values in practice (which is why this worked in testing
    # without this), but the Win32 API contract does not guarantee that, so declare the
    # real signatures explicitly rather than relying on it.
    dll.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    dll.CreateMutexW.restype = wintypes.HANDLE
    dll.ReleaseMutex.argtypes = [wintypes.HANDLE]
    dll.ReleaseMutex.restype = wintypes.BOOL
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.restype = wintypes.BOOL
    return dll


class SingleInstanceLock:
    """
    Guarantees only one process on the machine holds this named mutex at a time.

    Safety properties:
    - If this process exits in ANY way - normal return, unhandled exception, or being
      forcibly killed (Task Manager, crash, power loss) - Windows itself releases
      ownership of the mutex automatically at the OS/kernel level. This does not
      depend on our cleanup code running at all, which is exactly what's needed for
      "unexpected shutdown" safety: there is no stale-lock-file to clean up by hand.
    - `release()` is still called explicitly on graceful shutdown (via try/finally in
      the caller) so the mutex is freed immediately rather than waiting on process
      teardown, and it's safe to call more than once.
    """

    def __init__(self, name: str = DEFAULT_MUTEX_NAME):
        self.name = name
        self._handle: Optional[int] = None
        self.acquired = False

    def acquire(self) -> bool:
        """
        Creates (or opens, if it already exists) the named mutex.
        Returns True if no other process currently holds it (safe to proceed),
        False if another instance already owns it (caller must not start
        heartbeat/sync and should exit).
        """
        kernel32 = _kernel32()
        ctypes.set_last_error(0)
        handle = kernel32.CreateMutexW(None, wintypes.BOOL(False), self.name)
        last_error = ctypes.get_last_error()

        if not handle:
            raise ctypes.WinError(last_error)

        self._handle = handle

        if last_error == ERROR_ALREADY_EXISTS:
            # Another process already owns this mutex. We hold a valid handle to the
            # same kernel object, but we are NOT the owner - close it immediately and
            # report failure so the caller never proceeds as if it were the sole instance.
            kernel32.CloseHandle(self._handle)
            self._handle = None
            self.acquired = False
            logger.warning(
                f"SINGLE_INSTANCE_LOCK_HELD name={self.name} - another daemon instance "
                f"is already running; this process will not start heartbeat or sync."
            )
            return False

        self.acquired = True
        logger.info(f"SINGLE_INSTANCE_LOCK_ACQUIRED name={self.name}")
        return True

    def release(self) -> None:
        """Releases and closes the mutex handle. Safe to call multiple times / even if never acquired."""
        if self._handle:
            kernel32 = _kernel32()
            kernel32.ReleaseMutex(self._handle)
            kernel32.CloseHandle(self._handle)
            self._handle = None
            logger.info(f"SINGLE_INSTANCE_LOCK_RELEASED name={self.name}")
        self.acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        self.release()
        return False
