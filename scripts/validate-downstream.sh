#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROFILE="${ROOT}/deploy/boneman"
PRODUCT="${ROOT}/ods"

required=(
  ".github/downstream-config-manifest.yml"
  "deploy/boneman/.env.template"
  "deploy/boneman/README.md"
  "deploy/boneman/docker-compose.override.yml"
  "deploy/boneman/install.sh"
  "deploy/boneman/litellm.yaml"
)
for path in "${required[@]}"; do
  [[ -e "${ROOT}/${path}" ]] || {
    printf 'FAIL missing downstream path: %s\n' "$path" >&2
    exit 1
  }
done

shellcheck "${PROFILE}/install.sh" "$0" "${ROOT}/scripts/rebuild-downstream.sh"

python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
import yaml

root = Path(sys.argv[1])
manifest = yaml.safe_load((root / ".github/downstream-config-manifest.yml").read_text())
override = yaml.safe_load((root / "deploy/boneman/docker-compose.override.yml").read_text())
litellm = yaml.safe_load((root / "deploy/boneman/litellm.yaml").read_text())

assert manifest["upstream"]["repository"] == "Osmantic/ODS"
assert manifest["upstream"]["installed_release"] == "v2.6.0"
assert manifest["downstream"]["branch"] == "boneman/macos-omlx"
assert manifest["preserved_contract"]["production_engine"] == "oMLX"
assert manifest["preserved_contract"]["host_endpoint"] == "http://127.0.0.1:18080/v1"
assert override["services"]["dashboard-api"]["environment"]["LLM_BACKEND"] == "omlx"
assert "host.docker.internal:18080" in (root / "deploy/boneman/docker-compose.override.yml").read_text()
assert litellm["model_list"]
PY

temporary_env="$(mktemp)"
trap 'rm -f "$temporary_env"' EXIT
cp "${PROFILE}/.env.template" "$temporary_env"
{
  echo "OMLX_API_KEY=validation-only"
  echo "LITELLM_KEY=validation-only"
  echo "WEBUI_SECRET=validation-only"
  echo "DASHBOARD_API_KEY=validation-only"
  echo "ODS_AGENT_KEY=validation-only"
  echo "ODS_SESSION_SECRET=validation-only"
  echo "SHIELD_API_KEY=validation-only"
  echo "TOKEN_SPY_API_KEY=validation-only"
  echo "SEARXNG_SECRET=validation-only"
} >> "$temporary_env"

(
  cd "$PRODUCT"
  docker compose \
    --env-file "$temporary_env" \
    -f docker-compose.base.yml \
    -f installers/macos/docker-compose.macos.yml \
    -f extensions/services/litellm/compose.yaml \
    -f extensions/services/searxng/compose.yaml \
    -f extensions/services/token-spy/compose.yaml \
    -f ../deploy/boneman/docker-compose.override.yml \
    config --quiet
)

printf 'PASS downstream ODS overlay and reconstruction contract\n'
