import argparse


def main() -> None:
    parser = argparse.ArgumentParser(prog="nevis-tiny-search")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the API server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    parser.parse_args()
    parser.exit(1, "nevis-tiny-search: serve is not implemented yet\n")
