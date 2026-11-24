import asyncio
from threading import Event

import httpx
import pytest

from nevis_search.api import create_app
from nevis_search.search import Client, Document, Search


def test_health_and_sqlite_writes_complete_during_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEVIS_SEARCH", "sqlite-substring")
    monkeypatch.delenv("NEVIS_STORE", raising=False)
    search = Search.search

    async def exercise_api() -> None:
        app = create_app()
        loop = asyncio.get_running_loop()
        search_started = asyncio.Event()
        release_search = Event()

        def paused_search(service: Search, query: str) -> list[Client | Document]:
            # Pause before entering the store, so this request holds no SQLite lock.
            loop.call_soon_threadsafe(search_started.set)
            if not release_search.wait(timeout=10):
                raise TimeoutError("test did not release the paused search")
            return search(service, query)

        monkeypatch.setattr(Search, "search", paused_search)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as http,
            asyncio.timeout(5),
        ):
            async with asyncio.TaskGroup() as requests:
                pending_search = requests.create_task(
                    http.get("/search", params={"q": "concurrent memo"})
                )
                try:
                    await search_started.wait()
                    health = await http.get("/health")
                    assert health.status_code == 200
                    assert health.json() == "ok"
                    client = await http.post(
                        "/clients",
                        json={
                            "first_name": "Jane",
                            "last_name": "Doe",
                            "email": "jane@example.com",
                        },
                    )
                    assert client.status_code == 201
                    document = await http.post(
                        f"/clients/{client.json()['id']}/documents",
                        json={"title": "Concurrent memo", "content": "Example"},
                    )
                    assert document.status_code == 201
                    assert not pending_search.done()
                finally:
                    release_search.set()

            response = pending_search.result()
            assert response.status_code == 200
            assert response.json() == [document.json()]

    asyncio.run(exercise_api())
