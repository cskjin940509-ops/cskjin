#!/usr/bin/env python3
"""Publish validated data, then wake its consumers without waiting for cron.

Only fixed data paths and main-branch workflows are allowed. No force push,
conflict resolution, cancelled running ledger job, or trading-rule bypass.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, time, timezone, timedelta
import json
import os
import re
from pathlib import Path
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CN = timezone(timedelta(hours=8))
CHANNELS = {
    "gateway": ("astock_gateway", "astock_snapshots/index.json"),
    "factors": ("astock_factors", "astock_premarket"),
    "radar": ("astock_radar", "astock_ai_portfolio", "astock_factors"),
    "radar-evidence": ("astock_radar", "astock_selection_evidence"),
    "portfolio": ("astock_ai_portfolio",),
    "trade-plan": ("astock_trade",),
    "execution": ("astock_execution",),
    "tail": ("astock_tail", "astock_gateway/yunai_live.json", "astock_gateway/latest.json"),
    # The market gateway owns its rolling quotes. Publishing a frozen cohort
    # must not also publish an older copy of those shared quote files.
    "official": ("astock_snapshots/index.json",),
    "tracking": ("astock_snapshots/index.json", "astock_tracking"),
    "reverify": ("astock_snapshots/index.json", "astock_gateway/validation"),
    "history": ("astock_history",),
}
# Directed acyclic graph: no consumer dispatches back to its producer.
# Core radar -> portfolio calculation already runs in the same process chain.
DEPENDENTS = {
    "radar-evidence": ("run-ai-shadow-auto.yml",),
    "gateway": ("run-ai-shadow-auto.yml", "run-trade-plan.yml",
                "run-execution-assistant.yml", "run-tail-decision.yml", "run-daily-strategy.yml"),
    "factors": ("run-intraday-radar.yml",),
    "tail": ("run-trade-plan.yml", "run-execution-assistant.yml"),
    "official": ("run-trade-plan.yml", "run-execution-assistant.yml", "update-strategy-tracking.yml"),
    "tracking": ("update-history-pattern-lab.yml",),
    "reverify": ("update-history-pattern-lab.yml",),
}


def targets(channel: str, now: datetime) -> tuple[str, ...]:
    """Avoid off-session event storms; consumers retain their own data gates.

    Weekday/time routing is NOT proof of an exchange trading day. Each strategy
    still checks its calendar, quote timestamps and session before acting.
    Research reacts even on weekends when repaired historical evidence arrives.
    """
    now = now.astimezone(CN)
    result = []
    for workflow in DEPENDENTS.get(channel, ()):
        if workflow == "update-history-pattern-lab.yml":
            result.append(workflow)
            continue
        if now.weekday() >= 5:
            continue
        clock = now.time()
        if workflow == "run-daily-strategy.yml" and not time(15) <= clock <= time(18):
            continue
        if workflow == "update-strategy-tracking.yml" and clock < time(15):
            continue
        if workflow == "run-tail-decision.yml" and not time(14, 30) <= clock <= time(15, 40):
            continue
        if workflow in ("run-ai-shadow-auto.yml", "run-execution-assistant.yml"):
            if not (time(9, 30) <= clock <= time(11, 30) or time(13) <= clock <= time(15, 22)):
                continue
        result.append(workflow)
    return tuple(result)


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", "-c", "user.name=astock-data-bot",
                           "-c", "user.email=actions@users.noreply.github.com", *args], cwd=root, text=True,
                          encoding="utf-8", errors="replace", timeout=120,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} failed ({result.returncode}): {safe_error(result)}")
    return result


def safe_error(result) -> str:
    text = (result.stderr or result.stdout or "no diagnostic output")
    for key, value in os.environ.items():
        if value and len(value) >= 4 and any(word in key.upper() for word in ("TOKEN", "PASSWORD", "SECRET")):
            text = text.replace(value, "[redacted]")
    text = re.sub(r"https?://[^\s]+", "[remote URL]", text)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*).*", r"\1[redacted]", text)
    return text[-2000:]


def tree_entry(root: Path, revision: str, path: str) -> str:
    return git(root, "ls-tree", revision, "--", path).stdout.strip()


def publish_revision(root: Path, base: str, revision: str, channel: str) -> str:
    """Apply only this producer's delta; reject concurrent edits of the same file.

    Rebase in the computation checkout fails when another step has dirty outputs.
    A disposable worktree keeps those outputs and the local recovery commit intact.
    """
    paths = git(root, "diff", "--name-only", "-z", base, revision).stdout.split("\0")
    paths = [path for path in paths if path]
    last_error = ""
    for _ in range(4):
        git(root, "fetch", "origin", "main")
        with tempfile.TemporaryDirectory(prefix="astock-publish-") as directory:
            work = Path(directory) / "publish"
            git(root, "worktree", "add", "--detach", str(work), "origin/main")
            try:
                for path in paths:
                    before = tree_entry(root, base, path)
                    local = tree_entry(root, revision, path)
                    remote = tree_entry(work, "HEAD", path)
                    if remote == local:
                        continue
                    if remote != before:
                        raise RuntimeError(f"Concurrent data conflict: {path}; local recovery commit {revision} retained")
                    if local:
                        git(work, "checkout", revision, "--", path)
                    else:
                        git(work, "rm", "--", path)
                if not git(work, "diff", "--cached", "--name-only").stdout.strip():
                    return git(work, "rev-parse", "HEAD").stdout.strip()
                git(work, "commit", "-m", f"Publish {channel} data on arrival")
                pushed = git(work, "push", "origin", "HEAD:main", check=False)
                if pushed.returncode == 0:
                    return git(work, "rev-parse", "HEAD").stdout.strip()
                last_error = safe_error(pushed)
            finally:
                # This worktree was created here and holds only our disposable copy.
                git(root, "worktree", "remove", "--force", str(work))
    raise RuntimeError(f"Publication failed after four bounded attempts: {last_error}; recovery commit {revision}")


def publish(channel: str, root: Path = ROOT) -> str | None:
    if channel == "official":
        return publish_official(root)
    pending = Path(git(root, "rev-parse", "--git-path", f"publication-{channel}.json").stdout.strip())
    if not pending.is_absolute():
        pending = root / pending
    recovered = None
    if pending.exists():
        saved = json.loads(pending.read_text(encoding="utf-8"))
        recovered = publish_revision(root, saved["base"], saved["revision"], channel)
        pending.unlink()
    paths = [p for p in CHANNELS[channel]
             if (root / p).exists() or git(root, "ls-files", "--", p).stdout.strip()]
    if not paths:
        return recovered
    # Never accidentally bundle another step's staged changes in this commit.
    if git(root, "diff", "--cached", "--name-only").stdout.strip():
        raise RuntimeError("Refusing publication with unrelated staged changes")
    git(root, "add", "--", *paths)
    if not git(root, "diff", "--cached", "--name-only").stdout.strip():
        return recovered
    base = git(root, "rev-parse", "HEAD").stdout.strip()
    git(root, "commit", "-m", f"Save {channel} computation for publication")
    revision = git(root, "rev-parse", "HEAD").stdout.strip()
    pending.write_text(json.dumps({"base": base, "revision": revision}), encoding="utf-8")
    published = publish_revision(root, base, revision, channel)
    pending.unlink()
    return published


def merge_cohorts(base: list, local: list, remote: list) -> list:
    """Merge independently changed dates, never overwrite a concurrent cohort.

    Existing remote dates and their newer tracking survive. Same-date concurrent
    edits are explicitly rejected, not resolved with an ours/theirs overwrite.
    """
    def indexed(rows):
        result = {}
        for row in rows:
            day = row.get("date")
            if not day or day in result:
                raise RuntimeError("Invalid or duplicate cohort date")
            result[day] = row
        return result
    before, changed, current = map(indexed, (base, local, remote))
    if set(before) - set(changed):
        raise RuntimeError("Refusing deletion of historical cohorts")
    for day, row in changed.items():
        old = before.get(day)
        if row == old:
            continue
        if day in current and current[day] != old and current[day] != row:
            raise RuntimeError(f"Concurrent cohort conflict for {day}; saved snapshot requires review")
        if day not in before and (row.get("status") != "Official" or
                (row.get("dataValidation") or {}).get("status") not in
                {"Verified", "VerifiedWithExclusions"}):
            raise RuntimeError(f"New cohort {day} lacks verified Official evidence")
        current[day] = row
    return [current[day] for day in sorted(current)]


def publish_official(root: Path) -> str | None:
    """Publish in an isolated worktree so dirty gateway outputs cannot block it."""
    path = "astock_snapshots/index.json"
    if git(root, "diff", "--cached", "--name-only").stdout.strip():
        raise RuntimeError("Refusing publication with unrelated staged changes")
    base = json.loads(git(root, "show", f"HEAD:{path}").stdout)
    local = json.loads((root / path).read_text(encoding="utf-8"))
    if base == local:
        return None
    for _ in range(4):
        git(root, "fetch", "origin", "main")
        with tempfile.TemporaryDirectory(prefix="astock-official-") as temp:
            work = Path(temp) / "publish"
            git(root, "worktree", "add", "--detach", str(work), "origin/main")
            try:
                remote = json.loads((work / path).read_text(encoding="utf-8"))
                merged = merge_cohorts(base, local, remote)
                if merged == remote:
                    # A previous attempt may have pushed successfully before a
                    # transport error. Still wake consumers for this local delta.
                    return git(work, "rev-parse", "HEAD").stdout.strip()
                (work / path).write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                git(work, "add", "--", path)
                git(work, "commit", "-m", "Publish verified Official cohort without rolling gateway writes")
                if git(work, "push", "origin", "HEAD:main", check=False).returncode == 0:
                    return git(work, "rev-parse", "HEAD").stdout.strip()
            finally:
                # Only this temporary clean worktree is removed; the original
                # computed snapshot remains untouched even after a conflict.
                git(root, "worktree", "remove", str(work))
    raise RuntimeError("Official publication failed after four attempts; local evidence retained")


def dispatch(workflow: str, repository: str, token: str) -> None:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repository}/actions/workflows/{workflow}/dispatches",
        data=json.dumps({"ref": "main"}).encode(), method="POST",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
    )
    # No sleep/backoff between available data and dispatch. A short transport
    # retry can duplicate delivery; serialized consumers always read latest main.
    for attempt in range(2):
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                if response.status != 204:
                    raise RuntimeError(f"Unexpected dispatch status {response.status}")
            return
        except Exception:
            if attempt:
                raise


def run(channel: str, root: Path = ROOT) -> dict:
    started = datetime.now(CN)
    revision = publish(channel, root)
    report = {"channel": channel, "publicationStartedAt": started.isoformat(),
              "revision": revision, "state": "published" if revision else "unchanged",
              "dispatched": [], "failed": []}
    if revision:
        report["publishedAt"] = datetime.now(CN).isoformat()
        consumers = targets(channel, datetime.now(CN))
        if consumers:
            token = os.environ.get("GH_TOKEN", "")
            repository = os.environ.get("GITHUB_REPOSITORY", "")
            if not token or not repository:
                raise RuntimeError("Data published but dispatch credentials missing; cron remains fallback")
            with ThreadPoolExecutor(max_workers=5) as pool:
                futures = {pool.submit(dispatch, workflow, repository, token): workflow for workflow in consumers}
                for future in as_completed(futures):
                    workflow = futures[future]
                    try:
                        future.result()
                        report["dispatched"].append(workflow)
                    except Exception as error:
                        # Do not print request objects/headers or tokens.
                        report["failed"].append({"workflow": workflow, "errorType": type(error).__name__})
    report["finishedAt"] = datetime.now(CN).isoformat()
    report["elapsedSeconds"] = round((datetime.now(CN) - started).total_seconds(), 3)
    print(json.dumps(report, ensure_ascii=False))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as output:
            output.write("\n```json\n" + json.dumps(report, ensure_ascii=False, indent=2) + "\n```\n")
    if report["failed"]:
        raise RuntimeError("Data published; one or more immediate dispatches failed (see summary); cron remains fallback")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=CHANNELS)
    args = parser.parse_args()
    run(args.channel)
