from pathlib import Path
import unittest


WORKFLOW = (
    Path(__file__).parents[1] / ".github/workflows/claude-review.yml"
).read_text()


class ClaudeReviewWorkflowSecurityTests(unittest.TestCase):
    def test_issue_comments_resolve_pr_context_and_require_trusted_association(self):
        self.assertIn("github.rest.pulls.get", WORKFLOW)
        self.assertIn('new Set(["OWNER", "MEMBER", "COLLABORATOR"])', WORKFLOW)
        self.assertIn("needs.resolve-review-context.outputs.authorized == 'true'", WORKFLOW)
        self.assertIn("needs.resolve-review-context.outputs.is_fork != 'true'", WORKFLOW)
        self.assertNotIn("API key absence signals fork PR", WORKFLOW)

    def test_sensitive_filenames_are_data_not_javascript_source(self):
        self.assertIn("SENSITIVE_FILES: ${{ needs.detect-high-stakes.outputs.sensitive_files }}", WORKFLOW)
        self.assertIn("const sensitiveFiles = process.env.SENSITIVE_FILES;", WORKFLOW)
        self.assertNotIn("const sensitiveFiles = `${{ needs.detect-high-stakes.outputs.sensitive_files }}`", WORKFLOW)

    def test_review_checkout_is_exact_and_does_not_persist_credentials(self):
        self.assertIn("ref: ${{ needs.resolve-review-context.outputs.head_sha }}", WORKFLOW)
        self.assertIn("persist-credentials: false", WORKFLOW)
