#!/bin/sh
# End-to-end Docker Compose check, independent of pytest and local Python.
set -eu
cd "$(dirname -- "$0")/.."

project=nevis-smoke-$$
NEVIS_HTTP_PORT=0
NEVIS_SEARCH=${NEVIS_SEARCH:-dense-e5}
export NEVIS_HTTP_PORT NEVIS_SEARCH

compose() {
    docker compose -p "$project" "$@"
}

cleanup() {
    status=$?
    if [ "$status" -ne 0 ]; then
        compose ps -a >&2 || :
        compose logs --no-color >&2 || :
    fi
    compose down --volumes --remove-orphans || {
        if [ "$status" -eq 0 ]; then status=1; fi
    }
    exit "$status"
}

command -v curl >/dev/null
command -v jq >/dev/null
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

compose up --build --wait --wait-timeout 90
base="http://$(compose port search 8000)"
request() {
    curl --silent --show-error --fail-with-body --max-time 15 "$@"
}
search() {
    request --get "$base/search" --data-urlencode "q=$1"
}

first_result_is() {
    response=$(search "$1")
    printf '%s\n' "$response" | jq -e --arg id "$2" '.[0].id == $id' >/dev/null || {
        printf 'Unexpected results for "%s": %s\n' "$1" "$response" >&2
        return 1
    }
}

health=$(request "$base/health")
[ "$health" = '"ok"' ]
client=$(request "$base/clients" \
    --json '{"first_name":"Jane","last_name":"Doe","email":"jane.doe@example.com"}')
client_id=$(printf '%s\n' "$client" | jq -er '.id | strings')
bill=$(request "$base/clients/$client_id/documents" \
    --json '{"title":"April utility bill","content":"Electricity charges for April."}')
bill_id=$(printf '%s\n' "$bill" | jq -er '.id | strings')
first_result_is 'jane.doe@example.com' "$client_id"
first_result_is 'Jane Doe proof of address' "$bill_id"

# This has no literal phrase match and no query rule, so it needs the ranker.
if [ "$NEVIS_SEARCH" = dense-e5 ]; then
    first_result_is 'April electricity charges' "$bill_id"
fi

printf 'Compose smoke check passed (%s).\n' "$NEVIS_SEARCH"
