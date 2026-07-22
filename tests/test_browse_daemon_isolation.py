#!/usr/bin/env python3
"""Live two-daemon acceptance coverage for session-safe browser self-heal."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BROWSE = ROOT / "tools" / "agent-browse" / "agent-browse"
DAEMON = ROOT / "tools" / "agent-browse" / "daemon.js"
TMP = Path(tempfile.gettempdir())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def env_for(session: str) -> dict[str, str]:
    env = os.environ.copy()
    env["AGENT_BROWSER_SESSION"] = session
    env["AGENT_BROWSER_HEADED"] = "0"
    return env


def run(session: str, *args: str, timeout: float = 25) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(BROWSE), *args],
        cwd=ROOT,
        env=env_for(session),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def checked(session: str, *args: str, timeout: float = 25) -> subprocess.CompletedProcess[str]:
    result = run(session, *args, timeout=timeout)
    require(result.returncode == 0, f"browse {session} {' '.join(args)} failed: {result.stderr or result.stdout}")
    return result


def pid_file(session: str) -> Path:
    return TMP / f"agent-browser-{session}.pid"


def socket_file(session: str) -> Path:
    return TMP / f"agent-browser-{session}.sock"


def read_pid(session: str) -> int:
    return int(pid_file(session).read_text(encoding="utf-8").strip())


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def wait_for(path: Path, timeout: float = 8) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {path}")


def title(session: str) -> str:
    payload = json.loads(checked(session, "--json", "get", "title").stdout)
    return str((payload.get("data") or payload.get("result") or {}).get("title", ""))


def open_page(session: str, title_text: str) -> None:
    url = f"data:text/html,<title>{title_text}</title><main>{title_text}</main>"
    checked(session, "open", url)
    require(title(session) == title_text, f"session {session} did not retain its own page")


def close_session(session: str) -> None:
    try:
        run(session, "close", timeout=8)
    except subprocess.TimeoutExpired:
        pass


def main() -> None:
    launcher_source = BROWSE.read_text(encoding="utf-8")
    require("pkill" not in launcher_source and "killall" not in launcher_source, "broad daemon kill returned")
    require(
        'daemon.js" --session "$SESSION" --socket "$SOCKET_PATH"' in launcher_source,
        "daemon launch argv does not expose session identity",
    )

    suffix = uuid.uuid4().hex[:8]
    session_a = f"isoA-{suffix}"
    session_b = f"isoB-{suffix}"
    idle_session = f"idle-{suffix}"
    reuse_session = f"reuse-{suffix}"
    missing_session = f"missing-{suffix}"
    sessions = [session_a, session_b, idle_session, reuse_session, missing_session]
    idle_daemon: subprocess.Popen[bytes] | None = None
    innocent: subprocess.Popen[bytes] | None = None

    try:
        open_page(session_a, "isolation-a-before")
        open_page(session_b, "isolation-b")
        pid_a_before = read_pid(session_a)
        pid_b = read_pid(session_b)
        socket_b_inode = socket_file(session_b).stat().st_ino

        os.kill(pid_a_before, signal.SIGSTOP)
        wedged_doctor = json.loads(checked(session_a, "doctor", "--json").stdout)
        require(wedged_doctor["state"] == "wedged", f"wedged daemon misdiagnosed: {wedged_doctor}")
        healed = checked(
            session_a,
            "open",
            "data:text/html,<title>isolation-a-after</title><main>healed</main>",
            timeout=20,
        )
        require(
            f"daemon for session '{session_a}' was wedged — auto-restarted" in healed.stderr,
            f"self-heal warning missing: {healed.stderr}",
        )
        pid_a_after = read_pid(session_a)
        require(pid_a_after != pid_a_before, "wedged session daemon was not replaced")
        require(title(session_a) == "isolation-a-after", "original command did not continue after self-heal")
        require(read_pid(session_b) == pid_b and alive(pid_b), "self-heal signaled session B")
        require(socket_file(session_b).stat().st_ino == socket_b_inode, "self-heal replaced session B socket")
        require(title(session_b) == "isolation-b", "self-heal changed session B page")

        checked(session_a, "restart", timeout=20)
        require(read_pid(session_b) == pid_b and alive(pid_b), "manual restart signaled session B")
        require(socket_file(session_b).stat().st_ino == socket_b_inode, "manual restart replaced session B socket")
        require(title(session_b) == "isolation-b", "manual restart changed session B page")

        idle_daemon = subprocess.Popen(
            ["node", str(DAEMON), "--session", idle_session, "--socket", str(socket_file(idle_session))],
            cwd=ROOT,
            env=env_for(idle_session),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        wait_for(socket_file(idle_session))
        idle_pid = read_pid(idle_session)
        doctor = json.loads(checked(idle_session, "doctor", "--json").stdout)
        require(doctor["state"] == "healthy-idle", f"idle daemon misdiagnosed: {doctor}")
        require(doctor["session"]["name"] == idle_session, f"doctor reported another session: {doctor}")
        require(doctor["pid"]["identity_verified"] is True, f"doctor did not verify daemon argv: {doctor}")
        require(doctor["daemon"]["pingable"] is True, f"idle daemon did not answer ping: {doctor}")
        require(doctor["browser"]["responsive"] is False, f"ping auto-launched a browser: {doctor}")
        open_page(idle_session, "idle-kept-pid")
        require(read_pid(idle_session) == idle_pid, "healthy-idle daemon was needlessly restarted")

        innocent = subprocess.Popen(["sleep", "30"])
        pid_file(reuse_session).write_text(f"{innocent.pid}\n", encoding="utf-8")
        open_page(reuse_session, "pid-reuse-safe")
        require(innocent.poll() is None, "identity-mismatched PID was signaled")
        require(read_pid(reuse_session) != innocent.pid, "identity-mismatched PID file was not replaced")

        open_page(missing_session, "socket-before")
        missing_pid = read_pid(missing_session)
        socket_file(missing_session).unlink()
        open_page(missing_session, "socket-after")
        require(read_pid(missing_session) != missing_pid, "verified daemon with missing socket was not restarted")

    finally:
        for session in sessions:
            close_session(session)
        if idle_daemon is not None and idle_daemon.poll() is None:
            idle_daemon.terminate()
        if innocent is not None and innocent.poll() is None:
            innocent.terminate()

    print("browse daemon isolation tests passed")


if __name__ == "__main__":
    main()
