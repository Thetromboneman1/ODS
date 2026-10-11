from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).parents[1]
VALIDATION = (ROOT / ".github/workflows/documentation-health.yml").read_text()
WRITER = (ROOT / ".github/workflows/documentation-health-write.yml").read_text()


class DocumentationWorkflowSecurityTests(unittest.TestCase):
    def test_documentation_validation_is_read_only(self):
        self.assertIn("permissions:\n  contents: read", VALIDATION)
        self.assertIn("persist-credentials: false", VALIDATION)
        self.assertNotIn("git add -A", VALIDATION)
        self.assertNotIn("git push", VALIDATION)

    def test_patch_covers_every_document_class_the_generator_can_repair(self):
        maintained_suffix_check = 'path.endswith((".md", ".mdx", ".html"))'
        self.assertIn(maintained_suffix_check, VALIDATION)
        self.assertIn(maintained_suffix_check, WRITER)
        self.assertIn('git diff --binary HEAD -- .', VALIDATION)
        self.assertNotIn('git diff --binary -- README.md docs/REPOSITORY_STATE.md docs/architecture', VALIDATION)
        self.assertIn('"docs/reference/"', VALIDATION)
        self.assertIn('"docs/reference/"', WRITER)

    def test_patch_command_keeps_new_files_and_staged_deletions(self):
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            removed = repository / "removed.md"
            removed.write_text("obsolete\n")
            subprocess.run(["git", "add", "removed.md"], cwd=repository, check=True)
            subprocess.run(
                ["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture"],
                cwd=repository,
                check=True,
            )
            removed.unlink()
            (repository / "added.md").write_text("generated\n")
            subprocess.run(["git", "add", "-N", "--all"], cwd=repository, check=True)

            patch = subprocess.check_output(
                ["git", "diff", "--binary", "HEAD", "--", "."], cwd=repository, text=True
            )
            self.assertIn("deleted file mode", patch)
            self.assertIn("new file mode", patch)

    def test_writer_separates_write_capability_from_generated_tip_verification(self):
        self.assertIn("workflow_run:", WRITER)
        self.assertIn("ref: ${{ github.event.workflow_run.head_sha }}", WRITER)
        self.assertIn("Default branch moved after validation", WRITER)
        self.assertIn('fetch origin "${DEFAULT_BRANCH}"', WRITER)
        self.assertEqual(WRITER.count('extraheader=AUTHORIZATION: basic ${auth_header}'), 2)
        write_job, verification_job = WRITER.split("  verify-generated-commit:")
        self.assertNotIn("documentation_health.py", write_job)
        self.assertIn("permissions:\n      contents: read", verification_job)
        self.assertIn("persist-credentials: false", verification_job)
        self.assertIn("ref: ${{ needs.apply.outputs.committed_sha }}", verification_job)
        self.assertIn("documentation_health.py --check", verification_job)
