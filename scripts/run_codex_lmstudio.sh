#!/usr/bin/env bash
set -euo pipefail

CODEX_ENV="${HOME}/.codex/.env"

if [[ -f "${CODEX_ENV}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${CODEX_ENV}"
  set +a
fi

exec codex --profile lmstudio "$@"
