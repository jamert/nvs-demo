import sys
from pathlib import Path
from textwrap import dedent

import pytest

from nevis_search.config import Config
from tests.harness.environment import environment
from tests.harness.search_api import Client
from tests.harness.server import HOST, api, running_server, unused_port


@pytest.mark.parametrize("search_config", ["postgres-substring"], indirect=True)
def test_postgres_environment_survives_api_restart(search_config: Config) -> None:
    env = environment(search_config)
    with api(env) as server, server.client() as search:
        client = search.create_client(Client.any())

    with api(env) as restarted, restarted.client() as search:
        assert search.find_client(client.email) == client


def test_server_retries_health_and_is_reaped_after_failed_assertion(
    tmp_path: Path,
) -> None:
    port = unused_port()
    # Drop the first probe, report unavailable on the second, then become ready.
    script = dedent("""
        import sys
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            requests = 0

            def do_GET(self):
                assert self.path == "/health"
                Handler.requests += 1
                if Handler.requests == 2:
                    self.send_error(503)
                elif Handler.requests > 2:
                    self.send_response(200)
                    self.end_headers()

        HTTPServer((sys.argv[1], int(sys.argv[2])), Handler).serve_forever()
    """)
    command = [sys.executable, "-c", script, HOST, str(port)]

    log_path = tmp_path / "server.log"
    with (
        pytest.raises(AssertionError, match="deliberate test failure"),
        running_server(command, port=port, log_path=log_path) as server,
    ):
        raise AssertionError("deliberate test failure")

    assert server.process.returncode is not None
    assert '"GET /health HTTP/1.1" 200' in log_path.read_text()


def test_server_startup_failure_reports_exit_and_output(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "raise SystemExit('deliberate startup failure')"]

    with (
        pytest.raises(
            pytest.fail.Exception, match="exited with code 1 before becoming ready"
        ) as error,
        running_server(command, port=unused_port(), log_path=tmp_path / "crash.log"),
    ):
        pytest.fail("A server that exited should never be yielded")

    assert error.value.pytrace is False
    assert str(error.value).endswith("Server output:\ndeliberate startup failure")
