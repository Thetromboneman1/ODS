#!/usr/bin/env python3
"""Unit tests for dependency pin enforcement."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "check-dependency-pins.py"


def load_module():
    spec = importlib.util.spec_from_file_location("check_dependency_pins", SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_repo_dependency_lock_passes() -> None:
    module = load_module()
    errors = module.check()
    assert errors == [], "\n".join(errors)


def test_malformed_lock_collections_are_rejected() -> None:
    module = load_module()
    for name in ("entries", "allow_latest", "allow_local_images", "allow_variable_refs"):
        for invalid in (None, "not-an-array", {"path": "compose.yaml"}, 1):
            lock = {"version": 1, name: invalid}
            errors = module._validate_lock_shape(lock, ROOT)
            assert f"{name} must be an array" in errors
            # Ref validation must not crash or treat mapping keys as entries.
            module.validate_refs([], lock)


def test_unallowlisted_latest_is_rejected() -> None:
    module = load_module()
    lock = {
        "entries": [],
        "allow_latest": [],
        "allow_local_images": [],
        "allow_variable_refs": [],
    }
    ref = module.ImageRef(
        path="compose.yaml",
        line=3,
        raw="postgres:latest",
        value="postgres:latest",
        source="compose image",
    )
    errors = module.validate_refs([ref], lock)
    assert any("latest tag requires allow_latest" in error for error in errors)


def test_variable_refs_must_be_documented() -> None:
    module = load_module()
    lock = {
        "entries": [
            {
                "path": "compose.yaml",
                "value": "postgres:17.9-alpine",
            }
        ],
        "allow_latest": [],
        "allow_local_images": [],
        "allow_variable_refs": [],
    }
    ref = module.ImageRef(
        path="compose.yaml",
        line=3,
        raw="${POSTGRES_IMAGE:-postgres:17.9-alpine}",
        value="postgres:17.9-alpine",
        source="compose image",
    )
    errors = module.validate_refs([ref], lock)
    assert any("variable image ref is not documented" in error for error in errors)


def test_ephemeral_sha_tags_are_rejected() -> None:
    module = load_module()
    lock = {
        "entries": [
            {
                "path": "extensions/services/hermes/compose.yaml",
                "value": "nousresearch/hermes-agent:sha-dd0923bb89ed2dd56f82cb63656a1323f6f42e6f",
            }
        ],
        "allow_latest": [],
        "allow_local_images": [],
        "allow_variable_refs": [],
    }
    ref = module.ImageRef(
        path="extensions/services/hermes/compose.yaml",
        line=6,
        raw="nousresearch/hermes-agent:sha-dd0923bb89ed2dd56f82cb63656a1323f6f42e6f",
        value="nousresearch/hermes-agent:sha-dd0923bb89ed2dd56f82cb63656a1323f6f42e6f",
        source="compose image",
    )
    errors = module.validate_refs([ref], lock)
    assert any("ephemeral sha-* image tags are not release-stable" in error for error in errors)


def test_ephemeral_sha256_length_tags_are_rejected() -> None:
    module = load_module()
    image = "nousresearch/hermes-agent:sha-" + ("a" * 64)
    lock = {
        "entries": [
            {
                "path": "extensions/services/hermes/compose.yaml",
                "value": image,
            }
        ],
        "allow_latest": [],
        "allow_local_images": [],
        "allow_variable_refs": [],
    }
    ref = module.ImageRef(
        path="extensions/services/hermes/compose.yaml",
        line=6,
        raw=image,
        value=image,
        source="compose image",
    )
    errors = module.validate_refs([ref], lock)
    assert any("ephemeral sha-* image tags are not release-stable" in error for error in errors)


def test_sha256_digest_pins_are_allowed() -> None:
    module = load_module()
    image = (
        "nousresearch/hermes-agent@sha256:"
        "6e399abf4ff587822b0ef0df11f36088fb928e17ac61556fe89beb68d48c378e"
    )
    lock = {
        "entries": [
            {
                "path": "extensions/services/hermes/compose.yaml",
                "value": image,
            }
        ],
        "allow_latest": [],
        "allow_local_images": [],
        "allow_variable_refs": [],
    }
    ref = module.ImageRef(
        path="extensions/services/hermes/compose.yaml",
        line=6,
        raw=image,
        value=image,
        source="compose image",
    )
    errors = module.validate_refs([ref], lock)
    assert errors == [], "\n".join(errors)


def test_extension_library_sha_tags_are_rejected() -> None:
    module = load_module()
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        config = root / "config"
        service = root / "extensions" / "library" / "services" / "example"
        config.mkdir()
        service.mkdir(parents=True)
        lock_path = config / "dependency-lock.json"
        lock_path.write_text(
            (
                '{"version": 1, "entries": [], "allow_latest": [], '
                '"allow_local_images": [], "allow_variable_refs": []}\n'
            ),
            encoding="utf-8",
        )
        (service / "compose.yaml").write_text(
            "services:\n  app:\n    image: example/runtime:sha-1234567890abcdef\n",
            encoding="utf-8",
        )

        errors = module.check(lock_path, root)

    assert any("ephemeral sha-* image tags are not release-stable" in error for error in errors)
    assert any(
        "extensions/library/services/example/compose.yaml:3" in error for error in errors
    )


def _write_synthetic_open_interpreter_dockerfile(root: Path, requirements: str) -> None:
    dockerfile = root / "extensions" / "library" / "services" / "open-interpreter" / "Dockerfile"
    dockerfile.parent.mkdir(parents=True)
    dockerfile.write_text(
        f"FROM python:3.12-slim\nRUN pip install --no-cache-dir {requirements}\n",
        encoding="utf-8",
    )


def test_open_interpreter_excludes_compromised_litellm_versions() -> None:
    module = load_module()
    synthetic_versions = {"1.82.6", "1.82.7", "1.82.8", "1.82.9"}
    requirement = "litellm!=1.82.7,!=1.82.8"
    excluded = module._excluded_versions(requirement, "litellm")
    assert synthetic_versions - excluded == {"1.82.6", "1.82.9"}

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(
            root, f"{' '.join(sorted(module.OPEN_INTERPRETER_REQUIREMENTS))} {requirement}"
        )
        assert module.validate_open_interpreter_litellm_guard(root) == []


def test_open_interpreter_rejects_vulnerable_or_split_constraints() -> None:
    module = load_module()
    direct_requirements = " ".join(sorted(module.OPEN_INTERPRETER_REQUIREMENTS))

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(root, direct_requirements)
        errors = module.validate_open_interpreter_litellm_guard(root)
        assert any("1.82.7" in error and "1.82.8" in error for error in errors)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(
            root,
            f"{direct_requirements}\nRUN pip install litellm!=1.82.7,!=1.82.8",
        )
        errors = module.validate_open_interpreter_litellm_guard(root)
        assert any("expected exactly one pip install transaction" in error for error in errors)

    override_commands = (
        "python3 -m pip",
        "/usr/local/bin/pip",
        "pip3.12",
        "/usr/local/bin/python3.12 -m pip",
        "pip --disable-pip-version-check",
        "python3 -m pip --disable-pip-version-check",
    )
    for command in override_commands:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_synthetic_open_interpreter_dockerfile(
                root,
                f"{direct_requirements} litellm!=1.82.7,!=1.82.8"
                f"\nRUN {command} install litellm==1.82.7",
            )
            errors = module.validate_open_interpreter_litellm_guard(root)
            assert any(
                "expected exactly one pip install transaction" in error for error in errors
            ), command

    override_run_instructions = (
        'RUN ["pip", "install", "litellm==1.82.7"]',
        "RUN sh -c 'pip install litellm==1.82.7'",
    )
    for instruction in override_run_instructions:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_synthetic_open_interpreter_dockerfile(
                root,
                f"{direct_requirements} litellm!=1.82.7,!=1.82.8\n{instruction}",
            )
            errors = module.validate_open_interpreter_litellm_guard(root)
            assert any(
                "expected exactly one pip token" in error
                for error in errors
            ), instruction

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(
            root,
            f"{direct_requirements} litellm!=1.82.7,!=1.82.8"
            " && sh -c 'pip install litellm==1.82.7'",
        )
        errors = module.validate_open_interpreter_litellm_guard(root)
        assert any("expected exactly one pip token" in error for error in errors)


def test_open_interpreter_rejects_direct_pin_drift() -> None:
    module = load_module()
    requirements = set(module.OPEN_INTERPRETER_REQUIREMENTS)
    requirements.remove("fastapi==0.111.0")
    requirements.add("fastapi==0.112.0")
    requirements.add("litellm!=1.82.7,!=1.82.8")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(root, " ".join(sorted(requirements)))
        errors = module.validate_open_interpreter_litellm_guard(root)
        assert any("fastapi==0.111.0" in error for error in errors)


def test_open_interpreter_requires_pkg_resources_compatibility_cap() -> None:
    module = load_module()
    requirements = set(module.OPEN_INTERPRETER_REQUIREMENTS)
    requirements.remove("setuptools<82")
    requirements.add("setuptools")
    requirements.add("litellm!=1.82.7,!=1.82.8")
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write_synthetic_open_interpreter_dockerfile(root, " ".join(sorted(requirements)))
        errors = module.validate_open_interpreter_litellm_guard(root)
        assert any("setuptools<82" in error for error in errors)


def main() -> int:
    tests = [
        test_repo_dependency_lock_passes,
        test_malformed_lock_collections_are_rejected,
        test_unallowlisted_latest_is_rejected,
        test_variable_refs_must_be_documented,
        test_ephemeral_sha_tags_are_rejected,
        test_ephemeral_sha256_length_tags_are_rejected,
        test_sha256_digest_pins_are_allowed,
        test_extension_library_sha_tags_are_rejected,
        test_open_interpreter_excludes_compromised_litellm_versions,
        test_open_interpreter_rejects_vulnerable_or_split_constraints,
        test_open_interpreter_rejects_direct_pin_drift,
        test_open_interpreter_requires_pkg_resources_compatibility_cap,
    ]
    for test in tests:
        test()
    print("[PASS] dependency pin tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
