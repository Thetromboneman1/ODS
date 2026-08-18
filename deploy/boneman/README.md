# Boneman macOS oMLX deployment

This profile installs ODS as an additive control plane on the local Apple
Silicon workstation. It keeps the existing oMLX runtime on
`127.0.0.1:18080` as the production inference engine and does not install or
start another llama-server, Ollama, Hermes, OpenClaw, or OpenCode instance.

The checkout is pinned to upstream stable release `v2.5.3`. The fork branch is
`boneman/macos-omlx`; `upstream` points to `Osmantic/ODS` and `origin` points to
`Thetromboneman1/ODS`.

## Endpoints

| Surface | URL | Purpose |
| --- | --- | --- |
| ODS chat | `http://127.0.0.1:3100` | Separate Open WebUI instance |
| ODS dashboard | `http://127.0.0.1:3101` | ODS control and status UI |
| Dashboard API | `http://127.0.0.1:3102` | ODS dashboard backend |
| ODS LiteLLM | `http://127.0.0.1:4100/v1` | Optional OpenAI gateway |
| Token Spy | `http://127.0.0.1:3105` | ODS usage surface |
| SearXNG | `http://127.0.0.1:8889` | ODS-local search service |

All ports bind to loopback. Existing services on `3000`, `8080`, `18080`,
`8002`, and `8010` remain unchanged.

## Model contract

| ODS alias | oMLX model | Role |
| --- | --- | --- |
| `default`, `reasoning` | `mlx-community--gemma-4-31b-it-4bit` | Reasoning |
| `coding` | `mlx-community--gemma-4-26b-a4b-it-4bit` | Coding |
| `fast` | `mlx-community--gemma-4-e4b-it-4bit` | Fast agent work |
| `utility` | `unsloth--gemma-4-E2B-it-UD-MLX-4bit` | Routing and utility |
| `qwen38` | `qwen38-27b-q6-k` through `host.docker.internal:8040` | Stock Q6_K specialist |
| `qwen38-uncensored` | `qwen38-27b-uncensored-q6-k` through `host.docker.internal:8041` | Uncensored Q6_K specialist |

The two Qwen aliases are explicit selections and do not replace the oMLX
defaults. Codex uses its separate hybrid provider on host port `8042` to combine
the paid subscription catalog with these same local model IDs. See the
[canonical architecture and current visual](https://github.com/Thetromboneman1/Boneman_Projects/blob/main/local-ai-platform/ARCHITECTURE.md#system-diagram).
The [shared Codex picker runbook](https://github.com/Thetromboneman1/Boneman_Projects/blob/main/docs/operations/codex-model-pickers.md)
documents the matching desktop, CLI, VS Code, and phone Remote lists.

## Operation

```bash
deploy/boneman/install.sh --apply
deploy/boneman/install.sh --audit
deploy/boneman/install.sh --stop
```

The installer generates `dream-server/.env` with mode `0600`. It reads the
existing oMLX credential from `~/.omlx/settings.json`, never prints it, and
does not commit the runtime file. ODS-specific generated keys stay in that
local runtime file. Public image pulls use a deployment-local empty Docker
credential configuration so a locked Docker Desktop credential helper cannot
block unattended repair. The canonical fleet repair loop and operational
prompt live in `Boneman_Projects`.

## Upgrade

Fetch upstream tags, review the next stable release, rebase this branch onto
the audited tag, then run the Boneman self-heal loop. Do not track upstream
`main` for the installed stack because it moves faster than the stable release
channel.
