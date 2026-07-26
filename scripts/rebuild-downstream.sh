#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
MODE="validate"

case "${1:-}" in
  "") ;;
  --validate) MODE="validate" ;;
  --apply) MODE="apply" ;;
  *)
    printf 'Usage: %s [--validate|--apply]\n' "$0" >&2
    exit 2
    ;;
esac

"${SCRIPT_DIR}/validate-downstream.sh"

if [[ "$MODE" == "apply" ]]; then
  "${ROOT}/deploy/boneman/install.sh" --apply
else
  printf 'PASS rebuild validation complete; production was not changed\n'
fi
