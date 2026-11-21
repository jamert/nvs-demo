import os
import shlex
import socket
import subprocess
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep

import httpx
import pytest

HOST = "127.0.0.1"


@dataclass(frozen=True)
class Server:
    process: subprocess.Popen[bytes]
    port: int

    def url(self, path: str) -> str:
        return f"http://{HOST}:{self.port}{path}"


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind((HOST, 0))
        return listener.getsockname()[1]


@contextmanager
def api() -> Generator[Server]:
    port = unused_port()
    with (
        TemporaryDirectory(prefix="nevis-test-") as directory,
        running_server(
            ["nevis-tiny-search", "serve", "--host", HOST, "--port", str(port)],
            port=port,
            log_path=Path(directory) / "server.log",
        ) as server,
    ):
        yield server


@contextmanager
def running_server(
    command: Sequence[str], *, port: int, log_path: Path
) -> Generator[Server]:
    # A file lets the child keep logging without blocking on an undrained pipe.
    with log_path.open("wb") as log:
        try:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
        except OSError as exc:
            pytest.fail(f"Could not launch {shlex.join(command)}: {exc}", pytrace=False)

        try:
            server = Server(process, port)
            reason = _startup_error(server)
            if reason is not None:
                pytest.fail(
                    f"{shlex.join(command)}: {reason}\n"
                    f"Server output:\n{_log_tail(log_path)}",
                    pytrace=False,
                )
            yield server
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)


def _startup_error(server: Server) -> str | None:
    url = server.url("/health")
    deadline = monotonic() + 5
    last_status = None
    with httpx.Client(trust_env=False) as client:
        while True:
            if (code := server.process.poll()) is not None:
                return f"exited with code {code} before becoming ready"

            remaining = deadline - monotonic()
            if remaining <= 0:
                reason = f"{url} did not return HTTP 200 within 5 seconds"
                if last_status is not None:
                    reason += f" (last status: {last_status})"
                return reason

            try:
                with client.stream("GET", url, timeout=min(0.2, remaining)) as response:
                    last_status = response.status_code
                    if last_status == 200:
                        return None
            except httpx.TransportError:
                pass

            sleep(min(0.05, max(0, deadline - monotonic())))


def _log_tail(log_path: Path) -> str:
    with log_path.open("rb") as log:
        size = log.seek(0, os.SEEK_END)
        log.seek(max(0, size - 4096))
        return log.read(4096).decode("utf-8", errors="replace").strip() or "(no output)"
