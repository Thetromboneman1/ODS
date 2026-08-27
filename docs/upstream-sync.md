# ODS Upstream Synchronization

Last audited: 2026-08-27

Authoritative upstream is `Osmantic/ODS`. The downstream branch
`boneman/macos-omlx` is intentionally pinned to audited stable releases and
does not follow upstream `main` automatically.

`.github/workflows/upstream-sync.yml` checks the latest stable release monthly
and on manual dispatch. A new upstream commit is merged only into
`automation/upstream-sync-<sha>`, the downstream profile is rebuilt and
validated, and a pull request is opened. Conflicts create or update an issue
and leave the default branch unchanged. The workflow never force-pushes or
deploys production.

Manual validation:

```bash
scripts/rebuild-downstream.sh --validate
```

Production promotion remains explicit:

```bash
scripts/rebuild-downstream.sh --apply
```

Review the configuration diff, validation output, image changes, ports, model
aliases, and secret references before promotion.
