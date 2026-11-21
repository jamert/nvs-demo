import pytest

from tests.harness.server import api


@pytest.mark.xfail(reason="serve is not implemented yet", strict=True)
def test_smoke() -> None:
    with api() as _server:
        pass
