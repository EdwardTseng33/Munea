import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).with_name("agent-lock.py")
SPEC = importlib.util.spec_from_file_location("agent_lock", SCRIPT)
agent_lock = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = agent_lock
SPEC.loader.exec_module(agent_lock)


class AgentLockTests(unittest.TestCase):
    def payload(self, task_id, branch, paths):
        now = agent_lock.utc_now()
        return {
            "task_id": task_id,
            "owner": "test-agent",
            "branch": branch,
            "contact": "thread:test",
            "status": "active",
            "started_at": agent_lock.iso_z(now),
            "lease_expires_at": agent_lock.iso_z(now + timedelta(hours=24)),
            "base_sha": "abc123",
            "paths": paths,
            "note": "test lock",
        }

    def test_scope_rules(self):
        self.assertTrue(agent_lock.scopes_overlap("web/", "web/src/app.js"))
        self.assertTrue(agent_lock.scopes_overlap("web/src/", "web/"))
        self.assertFalse(agent_lock.scopes_overlap("web/", "engine/server.py"))
        self.assertTrue(agent_lock.scope_contains("app-site/", "app-site/index.html"))
        with self.assertRaises(agent_lock.LockError):
            agent_lock.normalize_scope("web/**/*.js")
        with self.assertRaises(agent_lock.LockError):
            agent_lock.normalize_scope("../secret")

    def test_overlap_is_blocking(self):
        lock = agent_lock.validate_payload(self.payload("web-task", "codex/web-task", ["web/"]))
        conflicts = agent_lock.conflicts_for("codex/other", ["web/src/app.js"], [lock])
        self.assertEqual(1, len(conflicts))
        self.assertEqual([], agent_lock.conflicts_for("codex/web-task", ["web/src/app.js"], [lock]))

    def test_lock_set_rejects_overlap_and_duplicate_branch(self):
        left = agent_lock.validate_payload(self.payload("left-task", "codex/left", ["web/"]))
        right = agent_lock.validate_payload(self.payload("right-task", "codex/right", ["web/src/app.js"]))
        with self.assertRaises(agent_lock.LockError):
            agent_lock.validate_lock_set([left, right])
        same_branch = agent_lock.validate_payload(self.payload("other-task", "codex/left", ["engine/"]))
        with self.assertRaises(agent_lock.LockError):
            agent_lock.validate_lock_set([left, same_branch])

    def test_worktree_loader_accepts_separate_scopes(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            os.chdir(temp)
            root = Path(".agent/locks/active")
            root.mkdir(parents=True)
            (root / "web-task.json").write_text(json.dumps(self.payload("web-task", "codex/web", ["web/"])), encoding="utf-8")
            (root / "engine-task.json").write_text(json.dumps(self.payload("engine-task", "codex/engine", ["engine/"])), encoding="utf-8")
            locks = agent_lock.load_worktree_locks()
            self.assertEqual({"web-task", "engine-task"}, {lock.task_id for lock in locks})
            os.chdir(previous)

    def make_git_repo(self, temp, branch="codex/web-task"):
        def run(*args):
            subprocess.run(args, cwd=temp, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        run("git", "init")
        run("git", "config", "user.email", "agent-test@example.com")
        run("git", "config", "user.name", "Agent Test")
        (Path(temp) / "scripts").mkdir()
        (Path(temp) / "scripts/agent-lock.py").write_text("# coordination tool\n", encoding="utf-8")
        lock_root = Path(temp) / ".agent/locks/active"
        lock_root.mkdir(parents=True)
        payload = self.payload("web-task", branch, ["web/"])
        (lock_root / "web-task.json").write_text(json.dumps(payload), encoding="utf-8")
        (Path(temp) / "web").mkdir()
        (Path(temp) / "web/index.html").write_text("before\n", encoding="utf-8")
        run("git", "add", ".")
        run("git", "commit", "-m", "base")
        base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
        run("git", "switch", "-c", branch)
        return run, base

    def test_ci_accepts_scoped_change_with_lock_release(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            run, base = self.make_git_repo(temp)
            (Path(temp) / "web/index.html").write_text("after\n", encoding="utf-8")
            (Path(temp) / ".agent/locks/active/web-task.json").unlink()
            run("git", "add", "-A")
            run("git", "commit", "-m", "finish")
            os.chdir(temp)
            result = agent_lock.command_ci(SimpleNamespace(base_ref=base, head_ref="HEAD", branch="codex/web-task"))
            os.chdir(previous)
            self.assertEqual(0, result)

    def test_ci_rejects_file_outside_owned_scope(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            run, base = self.make_git_repo(temp)
            (Path(temp) / "engine").mkdir()
            (Path(temp) / "engine/server.py").write_text("outside\n", encoding="utf-8")
            (Path(temp) / ".agent/locks/active/web-task.json").unlink()
            run("git", "add", "-A")
            run("git", "commit", "-m", "scope creep")
            os.chdir(temp)
            with self.assertRaises(agent_lock.LockError):
                agent_lock.command_ci(SimpleNamespace(base_ref=base, head_ref="HEAD", branch="codex/web-task"))
            os.chdir(previous)

    def test_ci_accepts_non_overlapping_lock_only_pr(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as temp:
            def run(*args):
                subprocess.run(args, cwd=temp, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

            run("git", "init")
            run("git", "config", "user.email", "agent-test@example.com")
            run("git", "config", "user.name", "Agent Test")
            (Path(temp) / "scripts").mkdir()
            (Path(temp) / "scripts/agent-lock.py").write_text("# coordination tool\n", encoding="utf-8")
            run("git", "add", ".")
            run("git", "commit", "-m", "base")
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=temp, check=True, text=True, stdout=subprocess.PIPE).stdout.strip()
            run("git", "switch", "-c", "codex/new-task")
            lock_root = Path(temp) / ".agent/locks/active"
            lock_root.mkdir(parents=True)
            (lock_root / "new-task.json").write_text(
                json.dumps(self.payload("new-task", "codex/new-task", ["app-site/"])),
                encoding="utf-8",
            )
            run("git", "add", ".")
            run("git", "commit", "-m", "claim lock")
            os.chdir(temp)
            result = agent_lock.command_ci(SimpleNamespace(base_ref=base, head_ref="HEAD", branch="codex/new-task"))
            os.chdir(previous)
            self.assertEqual(0, result)


if __name__ == "__main__":
    unittest.main()
