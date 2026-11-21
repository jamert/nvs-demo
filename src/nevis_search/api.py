from fastapi import APIRouter, FastAPI

router = APIRouter()


@router.get("/health", include_in_schema=False)
async def health() -> str:
    return "ok"


def create_app() -> FastAPI:
    app = FastAPI(title="Nevis Tiny Search")
    app.include_router(router)
    return app
