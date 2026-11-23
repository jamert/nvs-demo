import argparse
import os

lazy import uvicorn

lazy from nevis_search.api import create_app
lazy from nevis_search.search.postgres import SearchStorePostgres

__all__ = ["main"]


def main() -> None:
    parser = argparse.ArgumentParser(prog="nevis-tiny-search")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    commands.add_parser(
        "backfill-document-dates",
        help="Extract missing statement period ends in PostgreSQL",
    )
    args = parser.parse_args()
    if args.command == "backfill-document-dates":
        if not (dsn := os.environ.get("NEVIS_POSTGRES_DSN")):
            parser.error("NEVIS_POSTGRES_DSN is required for backfill-document-dates")
        with SearchStorePostgres.connect(dsn) as store:
            print(f"Updated {store.backfill_document_dates()} document dates.")
        return
    uvicorn.run(
        create_app,
        factory=True,
        host=args.host,
        port=args.port,
    )
