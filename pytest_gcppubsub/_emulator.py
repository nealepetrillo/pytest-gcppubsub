"""PubSub emulator subprocess management with xdist coordination."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from filelock import FileLock


@dataclass(frozen=True)
class EmulatorInfo:
    """Connection details for a running PubSub emulator."""

    host: str
    port: int
    project: str

    @property
    def host_port(self) -> str:
        return f"{self.host}:{self.port}"


def _find_free_port() -> int:
    """Find an available port by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port: int = s.getsockname()[1]
        return port


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_port(host: str, port: int, timeout: float) -> None:
    """Poll until the emulator port is accepting connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return
        except OSError:
            time.sleep(0.2)
    msg = f"Emulator did not start within {timeout}s on {host}:{port}"
    raise TimeoutError(msg)


def _terminate_process(pid: int, timeout: float = 5.0) -> None:
    """Terminate a process: SIGTERM, wait, then SIGKILL if needed."""
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _is_pid_alive(pid):
            return
        time.sleep(0.2)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class PubSubEmulator:
    """Manages the lifecycle of a GCP PubSub emulator subprocess.

    When ``shared_dir`` is provided, coordinates across pytest-xdist workers
    using a file lock and shared JSON state.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8085,
        project: str = "test-project",
        timeout: float = 15.0,
        shared_dir: Path | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._project = project
        self._timeout = timeout
        self._shared_dir = shared_dir
        self._process: subprocess.Popen[bytes] | None = None
        self._info: EmulatorInfo | None = None
        self._is_owner = False

    @property
    def info(self) -> EmulatorInfo:
        if self._info is None:
            msg = "Emulator has not been started"
            raise RuntimeError(msg)
        return self._info

    def start(self) -> EmulatorInfo:
        """Start the emulator, coordinating with xdist workers if needed."""
        if self._shared_dir is not None:
            return self._start_shared()
        return self._start_standalone()

    def stop(self) -> None:
        """Stop the emulator, coordinating with xdist workers if needed."""
        if self._shared_dir is not None:
            self._stop_shared()
        else:
            self._stop_standalone()

    def _start_standalone(self) -> EmulatorInfo:
        """Start a standalone emulator (no xdist)."""
        port = _find_free_port() if self._port == 0 else self._port
        self._process = self._launch(self._host, port, self._project)
        self._is_owner = True
        _wait_for_port(self._host, port, self._timeout)
        self._info = EmulatorInfo(
            host=self._host, port=port, project=self._project
        )
        return self._info

    def _stop_standalone(self) -> None:
        """Stop a standalone emulator."""
        if self._process is not None:
            _terminate_process(self._process.pid)
            self._process = None

    def _start_shared(self) -> EmulatorInfo:
        """Start or join a shared emulator (xdist mode)."""
        assert self._shared_dir is not None
        lock_path = self._shared_dir / "pubsub_emulator.lock"
        state_path = self._shared_dir / "pubsub_emulator.json"

        lock = FileLock(str(lock_path))
        with lock:
            state = self._read_state(state_path)
            if state is not None and _is_pid_alive(state["pid"]):
                # Join existing emulator
                state["worker_count"] += 1
                self._write_state(state_path, state)
                self._info = EmulatorInfo(
                    host=state["host"],
                    port=state["port"],
                    project=state["project"],
                )
                return self._info

            # Start new emulator (first worker or stale state)
            port = _find_free_port() if self._port == 0 else self._port
            self._process = self._launch(self._host, port, self._project)
            self._is_owner = True
            _wait_for_port(self._host, port, self._timeout)
            self._info = EmulatorInfo(
                host=self._host, port=port, project=self._project
            )
            self._write_state(
                state_path,
                {
                    "pid": self._process.pid,
                    "host": self._host,
                    "port": port,
                    "project": self._project,
                    "worker_count": 1,
                },
            )
            return self._info

    def _stop_shared(self) -> None:
        """Leave or stop a shared emulator (xdist mode)."""
        assert self._shared_dir is not None
        lock_path = self._shared_dir / "pubsub_emulator.lock"
        state_path = self._shared_dir / "pubsub_emulator.json"

        lock = FileLock(str(lock_path))
        with lock:
            state = self._read_state(state_path)
            if state is None:
                return
            state["worker_count"] -= 1
            if state["worker_count"] <= 0:
                _terminate_process(state["pid"])
                state_path.unlink(missing_ok=True)
            else:
                self._write_state(state_path, state)

    @staticmethod
    def _launch(
        host: str, port: int, project: str
    ) -> subprocess.Popen[bytes]:
        """Launch the gcloud PubSub emulator subprocess."""
        cmd = [
            "gcloud",
            "beta",
            "emulators",
            "pubsub",
            "start",
            f"--host-port={host}:{port}",
            f"--project={project}",
        ]
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    @staticmethod
    def _read_state(path: Path) -> dict[str, Any] | None:
        """Read shared state from JSON file."""
        try:
            return json.loads(path.read_text())  # type: ignore[no-any-return]
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_state(path: Path, state: dict[str, Any]) -> None:
        """Write shared state to JSON file."""
        path.write_text(json.dumps(state))
