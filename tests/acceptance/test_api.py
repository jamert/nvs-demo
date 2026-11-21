from tests.harness.server import api


def test_smoke() -> None:
    with api():  # Waits for GET /health to return HTTP 200.
        pass
