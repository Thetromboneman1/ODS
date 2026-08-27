#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PRODUCT_ROOT="${REPO_ROOT}/ods"
ENV_FILE="${PRODUCT_ROOT}/.env"
OMLX_SETTINGS="${OMLX_SETTINGS:-${HOME}/.omlx/settings.json}"
export DOCKER_CONFIG="${ODS_DOCKER_CONFIG:-${SCRIPT_DIR}/docker-public-config}"
MODE="apply"

usage() {
  cat <<'EOF'
Usage: deploy/boneman/install.sh [--audit|--apply|--stop]

Install or validate the additive Boneman ODS profile. The profile keeps oMLX
as the production inference engine and does not install another local model,
OpenCode service, Hermes instance, or OpenClaw instance.
EOF
}

while (($#)); do
  case "$1" in
    --audit) MODE="audit" ;;
    --apply) MODE="apply" ;;
    --stop) MODE="stop" ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

for required in docker jq curl openssl; do
  command -v "$required" >/dev/null 2>&1 || {
    printf 'BLOCKED missing command: %s\n' "$required" >&2
    exit 2
  }
done

compose_flags=(
  -f docker-compose.base.yml
  -f installers/macos/docker-compose.macos.yml
  -f extensions/services/litellm/compose.yaml
  -f extensions/services/searxng/compose.yaml
  -f extensions/services/token-spy/compose.yaml
  -f ../deploy/boneman/docker-compose.override.yml
)

write_secret_env() {
  local omlx_key
  [[ -r "$OMLX_SETTINGS" ]] || {
    printf 'BLOCKED missing oMLX settings: %s\n' "$OMLX_SETTINGS" >&2
    return 1
  }
  omlx_key="$(jq -er '.auth.api_key | select(length > 0)' "$OMLX_SETTINGS")"

  umask 077
  cp "$SCRIPT_DIR/.env.template" "$ENV_FILE"
  {
    printf 'OMLX_API_KEY=%s\n' "$omlx_key"
    printf 'WEBUI_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'DASHBOARD_API_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'ODS_AGENT_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'ODS_SESSION_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'SHIELD_API_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'TOKEN_SPY_API_KEY=%s\n' "$(openssl rand -hex 32)"
    printf 'SEARXNG_SECRET=%s\n' "$(openssl rand -hex 32)"
    printf 'LITELLM_KEY=sk-ods-%s\n' "$(openssl rand -hex 16)"
  } >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  unset omlx_key
}

ensure_env() {
  if [[ ! -s "$ENV_FILE" ]]; then
    [[ "$MODE" == "apply" ]] || {
      printf 'FAIL runtime env missing: %s\n' "$ENV_FILE"
      return 1
    }
    write_secret_env
    printf 'REPAIR generated runtime env mode=0600\n'
  fi
  [[ "$(stat -f '%Lp' "$ENV_FILE")" == "600" ]] || {
    [[ "$MODE" == "apply" ]] || {
      printf 'FAIL runtime env mode expected=600\n'
      return 1
    }
    chmod 600 "$ENV_FILE"
  }
}

probe_omlx() {
  local key probe_code
  key="$(jq -er '.auth.api_key | select(length > 0)' "$OMLX_SETTINGS")"
  probe_code="$(curl -sS -o /tmp/ods-omlx-models.json -w '%{http_code}' \
    -H "Authorization: Bearer ${key}" http://127.0.0.1:18080/v1/models)"
  unset key
  [[ "$probe_code" == "200" ]] || {
    printf 'FAIL oMLX models status=%s\n' "$probe_code"
    return 1
  }
  for model in \
    mlx-community--gemma-4-31b-it-4bit \
    mlx-community--gemma-4-26b-a4b-it-4bit \
    mlx-community--gemma-4-e4b-it-4bit \
    unsloth--gemma-4-E2B-it-UD-MLX-4bit; do
    jq -e --arg model "$model" '.data | any(.id == $model)' \
      /tmp/ods-omlx-models.json >/dev/null || {
      printf 'FAIL oMLX required model missing: %s\n' "$model"
      return 1
    }
  done
  printf 'PASS oMLX endpoint and Gemma role models\n'
}

probe_surface() {
  local name="$1" url="$2" expected="${3:-200}" probe_code attempt
  for attempt in 1 2 3 4 5 6 7 8 9 10 11 12; do
    probe_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "$url" || true)"
    if [[ "$probe_code" == "$expected" ]]; then
      printf 'PASS surface=%s status=%s url=%s\n' "$name" "$probe_code" "$url"
      return 0
    fi
    [[ "$attempt" -lt 12 ]] && sleep 5
  done
  printf 'FAIL surface=%s status=%s expected=%s url=%s\n' \
    "$name" "${probe_code:-unreachable}" "$expected" "$url"
  return 1
}

probe_gateway() {
  local gateway_key probe_code chat_code chat_content
  gateway_key="$(sed -n 's/^LITELLM_KEY=//p' "$ENV_FILE" | head -1)"
  probe_code="$(curl -sS -o /tmp/ods-litellm-models.json -w '%{http_code}' \
    --max-time 30 -H "Authorization: Bearer ${gateway_key}" \
    http://127.0.0.1:4100/v1/models || true)"
  [[ "$probe_code" == "200" ]] || {
    unset gateway_key
    printf 'FAIL ODS gateway models status=%s\n' "${probe_code:-unreachable}"
    return 1
  }
  for alias in default reasoning coding fast utility; do
    jq -e --arg alias "$alias" '.data | any(.id == $alias)' \
      /tmp/ods-litellm-models.json >/dev/null || {
      printf 'FAIL ODS gateway alias missing: %s\n' "$alias"
      return 1
    }
  done
  chat_code="$(curl -sS -o /tmp/ods-litellm-chat.json -w '%{http_code}' \
    --max-time 180 -H "Authorization: Bearer ${gateway_key}" \
    -H 'Content-Type: application/json' \
    -d '{"model":"fast","messages":[{"role":"user","content":"Reply exactly: ODS ready"}],"max_tokens":16,"temperature":0}' \
    http://127.0.0.1:4100/v1/chat/completions || true)"
  unset gateway_key
  chat_content="$(jq -r '.choices[0].message.content // empty' /tmp/ods-litellm-chat.json)"
  [[ "$chat_code" == "200" && "$chat_content" == "ODS ready" ]] || {
    printf 'FAIL ODS gateway chat status=%s content=%s\n' \
      "${chat_code:-unreachable}" "${chat_content:-missing}"
    return 1
  }
  printf 'PASS ODS gateway aliases=default,reasoning,coding,fast,utility chat=exact\n'
}

audit() {
  local failures=0
  ensure_env || failures=$((failures + 1))
  probe_omlx || failures=$((failures + 1))
  probe_surface webui http://127.0.0.1:3100/health || failures=$((failures + 1))
  probe_surface dashboard http://127.0.0.1:3101/ || failures=$((failures + 1))
  probe_surface dashboard-api http://127.0.0.1:3102/health || failures=$((failures + 1))
  probe_surface searxng http://127.0.0.1:8889/ || failures=$((failures + 1))
  probe_surface token-spy http://127.0.0.1:3105/health || failures=$((failures + 1))
  probe_gateway || failures=$((failures + 1))
  return "$failures"
}

cd "$PRODUCT_ROOT"

if [[ "$MODE" == "stop" ]]; then
  ensure_env
  docker compose "${compose_flags[@]}" down
  exit 0
fi

if [[ "$MODE" == "apply" ]]; then
  ensure_env
  probe_omlx
  cp "$SCRIPT_DIR/litellm.yaml" "$PRODUCT_ROOT/config/litellm/boneman.yaml"
  docker compose "${compose_flags[@]}" config --quiet
  docker compose "${compose_flags[@]}" pull --ignore-buildable
  docker compose "${compose_flags[@]}" build dashboard dashboard-api token-spy
  docker compose "${compose_flags[@]}" up -d --remove-orphans
fi

audit
