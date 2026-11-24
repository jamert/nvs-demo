#!/bin/sh
# Seed the evaluation documents through HTTP and check search on a fresh stack.
set -eu
cd "$(dirname -- "$0")/.."

project=nevis-search-eval-$$
NEVIS_HTTP_PORT=0
NEVIS_SEARCH=${NEVIS_SEARCH:-dense-e5}
export NEVIS_HTTP_PORT NEVIS_SEARCH

compose() {
    docker compose -p "$project" "$@"
}

cleanup() {
    status=$?
    if [ "$status" -ne 0 ]; then
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
    curl --silent --show-error --fail-with-body --max-time 30 "$@"
}

create_client() {
    payload=$(jq -nc --arg first "$1" --arg last "$2" --arg email "$3" \
        '{first_name: $first, last_name: $last, email: $email}') || return
    response=$(request "$base/clients" --json "$payload") || return
    printf '%s\n' "$response" | jq -er '.id | strings'
}

jamie=$(create_client Jamie Krag jamie.krag@example.com)
aimee=$(create_client Aimee Smith-Krag aimee.smith-krag@example.com)
karen=$(create_client Karen Reed karen.reed@example.com)
# The API has no joint ownership. Attach shared rows to a separate demo client.
household=$(create_client Krag Household krag.household@example.com)
test_client=$(create_client Test Client test@example.com)

add_document() {
    payload=$(printf '%s\n' "$2" | jq -ec '{title, content}') || return
    response=$(request "$base/clients/$1/documents" --json "$payload") || return
    printf '%s\n' "$response" | jq -er '.id | strings'
}

seed_documents() {
    # The frozen holdout snapshot repeats documents already in these JSONL files.
    for fixture in evals/cases/krag.jsonl evals/cases/reed.jsonl evals/cases/advisor-second-batch.jsonl; do
        while IFS= read -r row || [ -n "$row" ]; do
            owner=$(printf '%s\n' "$row" | jq -er '.owner') || return
            case "$owner" in
                jamie) client=$jamie ;;
                aimee) client=$aimee ;;
                karen) client=$karen ;;
                household) client=$household ;;
                *) printf 'Unknown owner in %s: %s\n' "$fixture" "$owner" >&2; return 1 ;;
            esac
            key=$(printf '%s\n' "$row" | jq -er '.key') || return
            id=$(add_document "$client" "$row") || return
            printf '%s\t%s\n' "$key" "$id"
        done < "$fixture"
    done
}

ids=$(seed_documents)
# The small exact-set corpus in evals/search_quality.py is not stored as JSONL.
add_document "$test_client" '{"title":"Electricity statement","content":"The electricity account shows usage for the service address."}' >/dev/null
add_document "$test_client" '{"title":"Water bill","content":"The current balance is for the service address."}' >/dev/null
add_document "$test_client" '{"title":"Investment report","content":"The portfolio gained value in the last quarter."}' >/dev/null
printf 'Seeded %s documents.\n' "$(printf '%s\n' "$ids" | awk 'END {print NR + 3}')"

document_id() {
    printf '%s\n' "$ids" | awk -F '\t' -v key="$1" '
        $1 == key {print $2; found = 1; exit}
        END {if (!found) exit 1}
    '
}

check_search() {
    query=$1 expected=$2 check=$3
    response=$(request --get "$base/search" --data-urlencode "q=$query")
    if ! printf '%s\n' "$response" | jq -e --arg id "$expected" --arg check "$check" '
        if $check == "first" then .[0].id == $id else any(.[]; .id == $id) end
    ' >/dev/null; then
        printf 'FAIL %s (expected ID %s, %s): %s\n' "$query" "$expected" "$check" "$response" >&2
        return 1
    fi
    printf 'PASS %s\n' "$query"
}

bill=$(document_id karen-electric-current)
statement=$(document_id jamie-401k-jun)
beneficiary=$(document_id karen-brokerage-tod)
follow_up=$(document_id jamie-follow-up-letter)
check_search 'Karen Reed' "$karen" first
check_search 'address proof' "$bill" anywhere
check_search 'Jamie Krag latest 401(k) statement' "$statement" first
check_search 'Reed who inherits account ending 0762' "$beneficiary" first
check_search 'Jamie Krag last appointment follow-ups' "$follow_up" first

printf 'Compose search checks passed (5/5, %s).\n' "$NEVIS_SEARCH"
