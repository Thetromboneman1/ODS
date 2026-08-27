# Boneman ODS Downstream Customizations

Last audited: 2026-08-27

The machine-readable contract is
`.github/downstream-config-manifest.yml`. The maintained overlay is
`deploy/boneman/`.

The downstream profile preserves:

- oMLX as the production inference engine at host port `18080`;
- the Gemma reasoning, coding, fast-agent, and utility role mapping;
- loopback-only ODS service bindings;
- collision-free ODS ports;
- the Docker-to-host `host.docker.internal` boundary;
- generated runtime secrets in `ods/.env` with mode `0600`; and
- manual production promotion.

Secret values are never stored in the manifest or repository. The installer
reads the existing oMLX credential and generates ODS-local runtime values. The
manifest records names only.

After an upstream merge, run `scripts/rebuild-downstream.sh --validate`. The
validator parses the manifest and YAML, runs ShellCheck, reconstructs the
Docker Compose model with disposable placeholder values, and verifies the
endpoint and model-role contract.
