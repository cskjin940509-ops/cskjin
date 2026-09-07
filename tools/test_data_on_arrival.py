import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import publish_data_on_arrival as arrival
import tracking_arrival_gate as gate
import enrich_slow_money_factors as factors


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        self.git(self.root, "init", "--bare", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.work))
        self.git(self.work, "checkout", "-b", "main")
        self.git(self.work, "config", "user.name", "Test")
        self.git(self.work, "config", "user.email", "test@example.invalid")
        (self.work / "astock_trade").mkdir()
        self.data = self.work / "astock_trade/latest.json"
        self.data.write_text('{"price": 1}\n')
        self.git(self.work, "add", ".")
        self.git(self.work, "commit", "-m", "initial")
        self.git(self.work, "push", "origin", "main")

    @staticmethod
    def git(root, *args):
        return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()

    def test_unchanged_does_not_commit_or_dispatch(self):
        before = self.git(self.work, "rev-parse", "HEAD")
        with patch.object(arrival, "dispatch") as dispatch, contextlib.redirect_stdout(io.StringIO()):
            result = arrival.run("trade-plan", self.work)
        self.assertEqual(result["state"], "unchanged")
        dispatch.assert_not_called()
        self.assertEqual(before, self.git(self.work, "rev-parse", "HEAD"))

    def test_new_and_deleted_files_publish_atomically(self):
        self.data.unlink()
        (self.work / "astock_trade/replacement.json").write_text('{"price": 2}')
        sha = arrival.publish("trade-plan", self.work)
        self.assertEqual(sha, self.git(self.remote, "rev-parse", "main"))
        files = self.git(self.remote, "ls-tree", "-r", "--name-only", "main")
        self.assertNotIn("latest.json", files)
        self.assertIn("replacement.json", files)

    def test_unrelated_remote_update_is_preserved(self):
        other = self.root / "other"
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        (other / "unrelated.txt").write_text("keep")
        self.git(other, "add", ".")
        self.git(other, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "other")
        self.git(other, "push", "origin", "main")
        self.data.write_text('{"price": 2}\n')
        arrival.publish("trade-plan", self.work)
        self.assertEqual("keep", self.git(self.remote, "show", "main:unrelated.txt"))

    def test_concurrent_same_file_conflict_never_overwrites(self):
        other = self.root / "other"
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        (other / "astock_trade/latest.json").write_text('{"price": 99}\n')
        self.git(other, "add", ".")
        self.git(other, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "other")
        self.git(other, "push", "origin", "main")
        self.data.write_text('{"price": 2}\n')
        with patch.object(arrival, "dispatch") as dispatch, self.assertRaisesRegex(RuntimeError, "conflict"):
            arrival.run("trade-plan", self.work)
        dispatch.assert_not_called()
        self.assertEqual('{"price": 99}', self.git(self.remote, "show", "main:astock_trade/latest.json"))

    def test_staged_code_cannot_enter_data_commit(self):
        (self.work / "code.py").write_text("unexpected")
        self.git(self.work, "add", "code.py")
        with self.assertRaisesRegex(RuntimeError, "staged"):
            arrival.publish("trade-plan", self.work)

    def test_official_ignores_dirty_and_concurrent_gateway_preserves_tracking(self):
        (self.work / "astock_snapshots").mkdir()
        index = self.work / "astock_snapshots/index.json"
        original = [{"date": "2026-09-03", "status": "Official", "tracking": 1}]
        index.write_text(json.dumps(original))
        (self.work / "astock_gateway").mkdir()
        gateway = self.work / "astock_gateway/latest.json"
        gateway.write_text('{"price": 1}')
        self.git(self.work, "add", ".")
        self.git(self.work, "commit", "-m", "fixtures")
        self.git(self.work, "push", "origin", "main")
        other = self.root / "other"
        self.git(self.root, "clone", "--branch", "main", str(self.remote), str(other))
        (other / "astock_gateway/latest.json").write_text('{"price": 99}')
        (other / "astock_snapshots/index.json").write_text(json.dumps([dict(original[0], tracking=2)]))
        self.git(other, "add", ".")
        self.git(other, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-m", "new quotes")
        self.git(other, "push", "origin", "main")
        new = {"date": "2026-09-04", "status": "Official", "dataValidation": {"status": "Verified"}}
        index.write_text(json.dumps(original + [new]))
        gateway.write_text('{"price": 2}')
        arrival.publish("official", self.work)
        self.assertEqual('{"price": 99}', self.git(self.remote, "show", "main:astock_gateway/latest.json"))
        result = json.loads(self.git(self.remote, "show", "main:astock_snapshots/index.json"))
        self.assertEqual(result, [dict(original[0], tracking=2), new])
        self.assertEqual('{"price": 2}', gateway.read_text())
        self.assertEqual(original + [new], json.loads(index.read_text()))

    def test_official_same_date_conflict_and_deletion_rejected(self):
        original = {"date": "2026-09-03", "status": "Official"}
        with self.assertRaisesRegex(RuntimeError, "conflict"):
            arrival.merge_cohorts([original], [dict(original, stocks=[1])], [dict(original, stocks=[2])])
        with self.assertRaisesRegex(RuntimeError, "deletion"):
            arrival.merge_cohorts([original], [], [original])

    def test_unverified_new_official_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "evidence"):
            arrival.merge_cohorts([], [{"date": "2026-09-04", "status": "Official"}], [])


class EventTests(unittest.TestCase):
    def test_dispatch_occurs_only_after_successful_publication(self):
        calls = []
        def publish(*args):
            calls.append("published")
            return "abc"
        def dispatch(*args):
            self.assertEqual(calls[0], "published")
            calls.append("dispatched")
        with patch.object(arrival, "publish", publish), patch.object(arrival, "dispatch", dispatch), \
             patch.object(arrival, "targets", return_value=("run-ai-shadow-auto.yml",)), \
             patch.dict(os.environ, {"GH_TOKEN": "fake", "GITHUB_REPOSITORY": "test/repo"}), \
             contextlib.redirect_stdout(io.StringIO()):
            result = arrival.run("gateway")
        self.assertEqual(result["failed"], [])
        self.assertEqual(calls, ["published", "dispatched"])

    def test_one_dispatch_failure_does_not_prevent_other_consumers(self):
        calls = []
        def dispatch(workflow, *args):
            calls.append(workflow)
            if workflow == "bad":
                raise OSError("network")
        with patch.object(arrival, "publish", return_value="abc"), patch.object(arrival, "dispatch", dispatch), \
             patch.object(arrival, "targets", return_value=("bad", "good")), \
             patch.dict(os.environ, {"GH_TOKEN": "fake", "GITHUB_REPOSITORY": "test/repo"}), \
             contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, "dispatches failed"):
            arrival.run("gateway")
        self.assertEqual(set(calls), {"bad", "good"})

    def test_route_close_research_and_session_separately(self):
        dt = lambda s: datetime.fromisoformat(s).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        morning = arrival.targets("gateway", dt("2026-09-07T10:00"))
        self.assertIn("run-ai-shadow-auto.yml", morning)
        self.assertNotIn("run-daily-strategy.yml", morning)
        self.assertNotIn("run-tail-decision.yml", morning)
        self.assertNotIn("run-ai-shadow-auto.yml", arrival.targets("gateway", dt("2026-09-07T12:00")))
        self.assertIn("run-daily-strategy.yml", arrival.targets("gateway", dt("2026-09-07T15:01")))
        self.assertEqual((), arrival.targets("gateway", dt("2026-09-06T10:00")))
        self.assertIn("update-history-pattern-lab.yml", arrival.targets("tracking", dt("2026-09-06T10:00")))


class CloseGateTests(unittest.TestCase):
    def test_early_tracking_requires_same_day_final_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            day = "2026-09-07"
            now = datetime.fromisoformat(day + "T15:01:00+08:00")
            self.assertFalse(gate.ready(now, root))
            data = {"verifiedToday": True, "closeFreeze": {"state": "ready", "date": day},
                    "marketSnapshot": {"sourceDate": day, "indices": {k: {"quoteTime": "14:59:59"} for k in gate.CORE}},
                    "boardHeatmap": {"industry": [1], "concept": [1]}}
            path = root / "astock_gateway/history" / (day + ".json")
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(data))
            self.assertFalse(gate.ready(now, root))
            for value in data["marketSnapshot"]["indices"].values():
                value["quoteTime"] = "15:00:00"
            path.write_text(json.dumps(data))
            self.assertTrue(gate.ready(now, root))
            self.assertFalse(gate.ready(now.replace(hour=14), root))
            data["closeFreeze"]["date"] = "2026-09-04"
            path.write_text(json.dumps(data))
            self.assertFalse(gate.ready(now, root))
            self.assertTrue(gate.ready(now.replace(minute=20), root))
            self.assertFalse(gate.ready(now.replace(day=6, minute=20), root))

    def test_slow_factors_keep_existing_four_day_ceiling(self):
        for day, expected in [("2026-09-04", True), ("2026-09-03", True), ("2026-09-02", False),
                              ("2026-09-07", False), ("2026-09-08", False), ("bad", False)]:
            with self.subTest(day=day), patch.object(factors, "load_for_signal_date", return_value={"dataDate": day}):
                self.assertEqual(expected, factors.usable_factors({"date": "2026-09-07"}))


class WorkflowTests(unittest.TestCase):
    def test_dispatch_targets_exist_and_graph_has_no_cycles(self):
        import yaml
        workflows = Path(__file__).resolve().parents[1] / ".github/workflows"
        producers = {}
        for path in workflows.glob("*.yml"):
            config = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
            if not isinstance(config, dict):
                continue
            channels = []
            for job in config.get("jobs", {}).values():
                for step in job.get("steps", []):
                    command = step.get("run", "")
                    if command.startswith("python tools/publish_data_on_arrival.py "):
                        channels.append(command.strip().split()[-1])
            if channels:
                self.assertEqual(config["permissions"]["actions"], "write")
                self.assertEqual(config["concurrency"]["cancel-in-progress"], "false")
                producers[path.name] = channels
        def visit(workflow, stack):
            self.assertNotIn(workflow, stack, "event dispatch loop")
            for channel in producers.get(workflow, []):
                self.assertIn(channel, arrival.CHANNELS)
                for target in arrival.DEPENDENTS.get(channel, ()):
                    config = yaml.load((workflows / target).read_text(), Loader=yaml.BaseLoader)
                    self.assertIn("workflow_dispatch", config["on"])
                    visit(target, stack + [workflow])
        for workflow in producers:
            visit(workflow, [])

    def test_validated_publication_precedes_slow_enrichment(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        for file, publish, slow in [
            ("run-intraday-radar.yml", "publish_data_on_arrival.py radar", "python tools/enrich_ai_shadow_benchmarks.py"),
            ("run-ai-shadow-auto.yml", "publish_data_on_arrival.py portfolio", "python tools/enrich_ai_shadow_benchmarks.py"),
            ("run-trade-plan.yml", "publish_data_on_arrival.py trade-plan", "python tools/augment_trade_plan_market_setups.py"),
            ("update-market-gateway.yml", "publish_data_on_arrival.py gateway", "python tools/enrich_yunai_gateway.py"),
            ("run-tail-decision.yml", "publish_data_on_arrival.py tail", "python tools/sync_yunai_production.py"),
        ]:
            text = (root / file).read_text()
            self.assertLess(text.index(publish), text.index(slow), file)
            if file.startswith("run-ai-") or file.startswith("run-intraday-"):
                self.assertLess(text.index("python tools/validate_ai_shadow_contract.py"), text.index(publish))
        self.assertNotIn("pip install", (root / "run-intraday-radar.yml").read_text())


if __name__ == "__main__":
    unittest.main()
