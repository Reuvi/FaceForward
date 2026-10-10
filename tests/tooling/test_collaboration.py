"""Exercise isolation and scope failures in disposable repositories only."""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[2] / "tools"


class CollaborationToolsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hackathon-tool-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo with spaces"
        self.repo.mkdir()
        self.run_git("init", "-b", "main")
        self.write(".gitignore", ".worktrees/\n")
        self.write("Vision/existing.txt", "base\n")
        self.write("Drivers/existing.txt", "base\n")
        self.commit("initial")

    def run_git(self, *args):
        return subprocess.run(
            ["git", *args], cwd=self.repo, check=True, text=True, capture_output=True
        ).stdout.strip()

    def write(self, name, content="test\n"):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def commit(self, message):
        self.run_git("add", "-A")
        self.run_git(
            "-c", "user.name=Tool Test", "-c", "user.email=tool-test@example.invalid",
            "commit", "-m", message,
        )

    def run_tool(self, script, *args, cwd=None):
        return subprocess.run(
            [sys.executable, str(TOOLS / script), *args], cwd=cwd or self.repo,
            text=True, capture_output=True,
        )

    def test_worktree_isolated_at_requested_base_and_duplicate_preserved(self):
        base = self.run_git("rev-parse", "HEAD")
        result = self.run_tool("new_worktree.py", "vision", "dev", "capture", "--base", "main")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.repo / ".worktrees/dev-vision-capture"
        self.assertEqual(self.run_git("branch", "--show-current"), "main")
        self.assertEqual(self.run_git("-C", str(target), "rev-parse", "HEAD"), base)
        self.assertEqual(self.run_git("status", "--porcelain"), "")
        (target / "Vision/existing.txt").write_text("agent work\n")
        self.assertEqual((self.repo / "Vision/existing.txt").read_text(), "base\n")
        duplicate = self.run_tool("new_worktree.py", "vision", "dev", "capture", "--base", "main")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertEqual((target / "Vision/existing.txt").read_text(), "agent work\n")

    def test_dirty_source_refused_without_losing_work(self):
        self.write("Vision/existing.txt", "unfinished\n")
        result = self.run_tool("new_worktree.py", "vision", "dev", "capture", "--base", "main")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.repo / "Vision/existing.txt").read_text(), "unfinished\n")
        self.assertFalse((self.repo / ".worktrees").exists())

    def test_invalid_slug_and_base_create_nothing(self):
        for developer, base in [("../escape", "main"), ("dev", "no-such-base")]:
            with self.subTest(developer=developer, base=base):
                result = self.run_tool("new_worktree.py", "vision", developer, "capture", "--base", base)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.repo / ".worktrees").exists())

    def test_scope_includes_committed_staged_unstaged_and_untracked(self):
        self.run_git("switch", "-c", "work/dev/vision/capture")
        self.write("Drivers/committed.txt")
        self.commit("outside lane")
        self.write("Drivers/staged.txt")
        self.run_git("add", "Drivers/staged.txt")
        self.write("Drivers/existing.txt", "unstaged\n")
        self.write("Drivers/untracked.txt")
        result = self.run_tool("check_scope.py", "--base", "main")
        self.assertEqual(result.returncode, 1)
        for name in ("committed.txt", "staged.txt", "existing.txt", "untracked.txt"):
            self.assertIn("Drivers/" + name, result.stderr)

    def test_allowed_scope_and_subdirectory_invocation(self):
        self.run_git("switch", "-c", "work/dev/vision/capture")
        self.write("Vision/new.txt")
        self.assertEqual(self.run_tool("check_scope.py", "--base", "main").returncode, 0)
        self.write("root-untracked.txt")
        result = self.run_tool("check_scope.py", "--base", "main", cwd=self.repo / "Vision")
        self.assertEqual(result.returncode, 1)
        self.assertIn("root-untracked.txt", result.stderr)

    def test_cross_lane_rename_checks_source_and_destination(self):
        self.run_git("mv", "Drivers/existing.txt", "Vision/renamed.txt")
        result = self.run_tool("check_scope.py", "--base", "main", "--lane", "vision")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Drivers/existing.txt", result.stderr)

    def test_integration_branch_and_unknown_branch(self):
        self.write("shared.txt")
        result = self.run_tool(
            "check_scope.py", "--base", "main", "--branch", "work/dev/integration/wiring"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        unknown = self.run_tool("check_scope.py", "--base", "main", "--branch", "unscoped")
        self.assertNotEqual(unknown.returncode, 0)


if __name__ == "__main__":
    unittest.main()
