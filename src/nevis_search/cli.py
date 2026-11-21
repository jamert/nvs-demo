import argparse

lazy import uvicorn

lazy from nevis_search.api import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="nevis-tiny-search")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(
        create_app,
        factory=True,
        host=args.host,
        port=args.port,
    )
