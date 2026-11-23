import subprocess
import sys
import time
import uuid

import pytest

from tally_sync_agent.core.single_instance import SingleInstanceLock

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows named mutex - Windows only")


def _unique_name() -> str:
    # "Local\\" (not "Global\\") so tests never need elevated/cross-session rights,
    # and a fresh uuid per test so tests can't collide with each other or with a real
    # running production daemon (which uses the DEFAULT_MUTEX_NAME, never this one).
    return f"Local\\FieldTrackTallyAgent_TEST_{uuid.uuid4().hex}"


def test_first_launch_acquires_successfully():
    name = _unique_name()
    lock = SingleInstanceLock(name=name)
    try:
        assert lock.acquire() is True
        assert lock.acquired is True
    finally:
        lock.release()


def test_duplicate_launch_is_detected_and_refused():
    """The exact scenario this feature exists for: a second process trying to start
    the daemon while one is already running must be told no, cleanly."""
    name = _unique_name()
    first = SingleInstanceLock(name=name)
    second = SingleInstanceLock(name=name)
    try:
        assert first.acquire() is True

        # The second instance must NOT be able to acquire it...
        assert second.acquire() is False
        assert second.acquired is False
        # ...and must not be left holding any handle that could interfere later.
        assert second._handle is None
    finally:
        first.release()
        second.release()  # safe no-op, never acquired


def test_mutex_is_released_after_graceful_shutdown_and_can_be_reacquired():
    """Simulates: daemon runs, stops gracefully (release() called), then a later
    launch must be able to acquire the now-free mutex - proving release() actually
    frees it rather than leaving it permanently held for the life of the name."""
    name = _unique_name()
    first = SingleInstanceLock(name=name)
    assert first.acquire() is True
    first.release()
    assert first.acquired is False

    second = SingleInstanceLock(name=name)
    try:
        assert second.acquire() is True
    finally:
        second.release()


def test_release_is_safe_to_call_multiple_times_and_without_acquiring():
    lock = SingleInstanceLock(name=_unique_name())
    lock.release()  # never acquired - must not raise
    lock.acquire()
    lock.release()
    lock.release()  # already released - must not raise


def test_mutex_is_auto_released_by_windows_when_owning_process_is_killed_abruptly():
    """
    Proves the "unexpected shutdown" safety property empirically rather than just
    documenting it: spawns a real child process that acquires the named mutex and
    then blocks forever, forcibly kills it (simulating a crash / Task Manager kill -
    NOT a graceful shutdown, so the child's own cleanup code never runs), and confirms
    this process can immediately acquire the same mutex afterward. If Windows did not
    auto-release mutexes on process death, this would hang/fail.
    """
    name = _unique_name()
    child_code = (
        "import ctypes, time\n"
        f"m = ctypes.windll.kernel32.CreateMutexW(None, False, {name!r})\n"
        "assert m\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", child_code])
    try:
        # Give the child a moment to actually acquire the mutex before killing it.
        time.sleep(1.5)
        proc.kill()  # abrupt, ungraceful termination - no cleanup code runs in the child
        proc.wait(timeout=10)

        lock = SingleInstanceLock(name=name)
        try:
            assert lock.acquire() is True, (
                "Mutex was not released by the OS after the owning process was killed"
            )
        finally:
            lock.release()
    finally:
        if proc.poll() is None:
            proc.kill()
