"""Regression tests for downstream validation coverage and failure reporting."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
VALIDATORS = (
    "secret-scan.yml",
    "lint-python.yml",
    "type-check-python.yml",
    "validate-catalog.yml",
    "validate-compose.yml",
)


def workflow(name):
    # BaseLoader preserves GitHub's `on` key rather than YAML 1.1's boolean.
    return yaml.load((WORKFLOWS / name).read_text(), Loader=yaml.BaseLoader)


class ValidationWorkflowTests(unittest.TestCase):
    def test_validators_cover_upstream_and_downstream(self):
        for name in VALIDATORS:
            for event in ("push", "pull_request"):
                with self.subTest(workflow=name, event=event):
                    branches = workflow(name)["on"][event]["branches"]
                    self.assertIn("main", branches)
                    self.assertIn("boneman/macos-omlx", branches)

    def test_path_filtered_validators_validate_their_own_changes(self):
        for name in VALIDATORS:
            for event in ("push", "pull_request"):
                with self.subTest(workflow=name, event=event):
                    paths = workflow(name)["on"][event].get("paths")
                    if paths:
                        self.assertIn(f".github/workflows/{name}", paths)

    def test_all_type_checks_are_independent_and_blocking(self):
        job = workflow("type-check-python.yml")["jobs"]["mypy"]
        self.assertNotEqual(job.get("continue-on-error"), "true")
        for step in job["steps"]:
            with self.subTest(step=step.get("name", step.get("uses"))):
                self.assertNotEqual(step.get("continue-on-error"), "true")
        self.assertIn("strategy", job, "Independent targets must all run even when one fails")
        self.assertEqual(job["strategy"]["fail-fast"], "false")
        targets = job["strategy"]["matrix"]["include"]
        self.assertEqual(
            {target["service"] for target in targets},
            {"dashboard-api", "token-spy", "privacy-shield", "scripts"},
        )

    def test_type_check_commands_propagate_failure(self):
        steps = workflow("type-check-python.yml")["jobs"]["mypy"]["steps"]
        commands = [step["run"] for step in steps if step.get("run", "").startswith("mypy ")]
        self.assertTrue(commands, "No standalone type-check commands found")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "mypy"
            executable.write_text("#!/bin/sh\nexit 3\n")
            executable.chmod(0o755)
            (root / "example.py").write_text("value = 1\n")
            env = {**os.environ, "PATH": directory + os.pathsep + os.environ["PATH"]}
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(
                        ["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", command],
                        cwd=root, env=env, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 3, result.stdout + result.stderr)

    def installer_syntax_step(self):
        steps = workflow("matrix-smoke.yml")["jobs"]["distro-matrix"]["steps"]
        return next(step["run"] for step in steps if step.get("name") == "Test installer bash syntax")

    def run_syntax_check(self, invalid=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = (
                "install-core.sh",
                "installers/lib/packaging.sh",
                "installers/phases/01-valid.sh",
                "installers/phases/02-check.sh",
                "installers/phases/03-valid.sh",
            )
            for script in scripts:
                path = root / script
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("if then\n" if script == invalid else "#!/bin/bash\ntrue\n")
            # Container run steps use sh -e unless a shell is explicitly set.
            return subprocess.run(
                ["sh", "-e", "-c", self.installer_syntax_step()],
                cwd=root, text=True, capture_output=True, check=False,
            )

    def test_valid_installer_scripts_pass(self):
        result = self.run_syntax_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_installer_scripts_fail(self):
        for script in (
            "install-core.sh",
            "installers/lib/packaging.sh",
            "installers/phases/02-check.sh",
        ):
            with self.subTest(script=script):
                result = self.run_syntax_check(invalid=script)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                if "/phases/" in script:
                    self.assertIn("FAIL: " + script, result.stdout)
                    self.assertIn("OK: installers/phases/03-valid.sh", result.stdout)


if __name__ == "__main__":
    unittest.main()
