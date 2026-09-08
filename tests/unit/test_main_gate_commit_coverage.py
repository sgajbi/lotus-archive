"""Guards for per-commit main-gate coverage (found by cross-repo review, 2026-08-31).

This repository merges by rebase, so a merged PR of N commits puts N commits
on main. The dispatcher previously named only ``merge_commit_sha`` - the
other N-1 commits had no releasability run, invisibly, because a run that is
never created is not a failure (archive#117; the class was measured across the
estate and fixed first in lotus-render#174, reference variant
lotus-report#221). These tests pin the two halves of the fix: the dispatcher
enumerates every merged revision, and the daily audit fails closed rather
than passing while verifying nothing.
"""

from __future__ import annotations

import argparse
import shutil
import shlex
import subprocess
from pathlib import Path

import pytest

from scripts import audit_main_gate_coverage as audit

pytestmark = pytest.mark.governance

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"


def test_merged_pr_dispatch_gates_every_revision_the_pr_put_on_main() -> None:
    dispatcher = (WORKFLOW_ROOT / "merged-pr-main-releasability.yml").read_text(encoding="utf-8")

    # Enumeration of every revision, oldest first, from full history.
    assert "COMMIT_COUNT: ${{ github.event.pull_request.commits }}" in dispatcher
    assert "BASE_SHA: ${{ github.event.pull_request.base.sha }}" in dispatcher
    assert 'git rev-list --reverse "$BASE_SHA..$MERGE_COMMIT_SHA"' in dispatcher
    # This assertion previously pinned `rev-list -n "$COMMIT_COUNT"`, which is
    # the defect (#162): the guard and its test were wrong together, so a
    # revert would have been invisible and the suite would have resisted the fix.
    assert 'git rev-list -n "$COMMIT_COUNT"' not in dispatcher, (
        "the count-bounded walk enumerates past the PR into earlier merges"
    )
    # The count survives as an ASYMMETRIC cross-check: more revisions than
    # declared is a wrong window and must fail; fewer is the ordinary rebase
    # case and must not.
    assert '"$revision_count" -gt "$COMMIT_COUNT"' in dispatcher
    assert '"$revision_count" -lt "$COMMIT_COUNT"' in dispatcher
    assert dispatcher.index('"$revision_count" -gt "$COMMIT_COUNT"') < dispatcher.index(
        "for revision in $revisions; do"
    ), "the window must be checked before anything is tagged or dispatched"
    assert "for revision in $revisions; do" in dispatcher
    assert "fetch-depth: 0" in dispatcher
    # Every dispatch is pinned to its own revision, not the PR head.
    assert 'dispatch_ref="main-releasability-${revision}"' in dispatcher
    assert '-f expected_sha="$revision"' in dispatcher
    # The enumeration is only correct under rebase-only merging; the
    # dispatcher must fail loudly if the repository setting ever changes.
    assert "allow_squash_merge" in dispatcher
    assert '"$merge_methods" != "false,false,true"' in dispatcher
    # Ancestry is judged against the freshly fetched main, and a revision that
    # is not main history is refused BEFORE any tag is created or gate
    # dispatched: the guard must sit inside the loop, after the detach onto
    # FETCH_HEAD and ahead of both the tag write and the workflow dispatch.
    assert "git checkout --quiet --detach FETCH_HEAD" in dispatcher
    guard = 'if ! git merge-base --is-ancestor "$revision" HEAD; then'
    assert guard in dispatcher
    assert dispatcher.index("git fetch origin main --quiet") < dispatcher.index(
        "git checkout --quiet --detach FETCH_HEAD"
    )
    assert dispatcher.index("for revision in $revisions; do") < dispatcher.index(guard)
    assert dispatcher.index(guard) < dispatcher.index(
        'dispatch_ref="main-releasability-${revision}"'
    )
    assert dispatcher.index(guard) < dispatcher.index('gh api "repos/$GITHUB_REPOSITORY/git/refs"')
    assert dispatcher.index(guard) < dispatcher.index("gh workflow run main-releasability.yml")


def test_coverage_audit_workflow_runs_the_fail_closed_audit() -> None:
    workflow = (WORKFLOW_ROOT / "main-gate-coverage-audit.yml").read_text(encoding="utf-8")

    assert "schedule:" in workflow
    assert "workflow_dispatch" in workflow
    assert "python scripts/audit_main_gate_coverage.py" in workflow
    assert "--fail-on-gap" in workflow


def test_audit_counts_only_verdict_bearing_runs_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A cancelled run evaluated nothing, an unfetchable listing proves
    nothing, and both must fail the audit rather than pass it."""

    commits = {
        "a" * 40: ["success"],
        "b" * 40: ["cancelled"],
        "c" * 40: None,
        "d" * 40: [],
    }
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: [f"{sha} {sha[:9]} subject line" for sha in commits],
    )
    monkeypatch.setattr(audit, "_run_conclusions", lambda sha: commits[sha])
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=400, since_days=7, fail_on_gap=True),
    )

    exit_code = audit.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "UNGATED  ddddddddd" in output
    assert "1 passing, 0 with a failing verdict" in output
    assert "UNKNOWN  ccccccccc" in output
    assert "UNKNOWN  bbbbbbbbb" in output
    assert "1 with no verdict-bearing" in output


def test_a_full_window_is_not_reported_as_truncated(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A window holding exactly --limit commits was fully examined; only a
    commit BEYOND the cap proves the span was cut short. Declaring truncation
    at equality would fail the scheduled audit for no reason."""

    shas = [f"{index:040x}" for index in range(3)]
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: [f"{sha} {sha[:9]} subject line" for sha in shas],
    )
    monkeypatch.setattr(audit, "_run_conclusions", lambda sha: ["success"])
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=3, since_days=7, fail_on_gap=True),
    )

    exit_code = audit.main()
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "WINDOW TRUNCATED" not in output


def test_a_window_beyond_the_cap_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    shas = [f"{index:040x}" for index in range(4)]
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: [f"{sha} {sha[:9]} subject line" for sha in shas],
    )
    monkeypatch.setattr(audit, "_run_conclusions", lambda sha: ["success"])
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=3, since_days=7, fail_on_gap=True),
    )

    exit_code = audit.main()
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "WINDOW TRUNCATED" in output
    assert "audited 3 commit(s)" in output


def test_the_window_walks_every_commit_regardless_of_date_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`--since` stops traversal at the first older commit, so a newer-dated
    ancestor behind an older-dated one is silently omitted - a green audit for
    a window it never walked. `--since-as-filter` visits every commit."""

    recorded: list[tuple[str, ...]] = []

    def _record(*args: str) -> list[str]:
        recorded.append(args)
        return []

    monkeypatch.setattr(audit, "_git", _record)
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=400, since_days=7, fail_on_gap=True),
    )

    audit.main()

    assert recorded, "the audit never asked git for the window"
    flags = recorded[0]
    assert any(flag.startswith("--since-as-filter=") for flag in flags), flags
    assert not any(flag.startswith("--since=") for flag in flags), (
        "plain --since truncates the window at the first older commit"
    )


def test_audit_fails_closed_when_gh_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=400, since_days=7, fail_on_gap=True),
    )

    assert audit.main() == 1


def test_audit_passes_when_every_commit_has_a_verdict(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failing verdict is information, not a coverage gap: the audit passes
    but reports the split so coverage and releasability stay distinct claims."""

    commits = {"a" * 40: ["success"], "b" * 40: ["failure", "cancelled"]}
    monkeypatch.setattr(
        audit,
        "_git",
        lambda *args: [f"{sha} {sha[:9]} subject line" for sha in commits],
    )
    monkeypatch.setattr(audit, "_run_conclusions", lambda sha: commits[sha])
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    monkeypatch.setattr(
        argparse.ArgumentParser,
        "parse_args",
        lambda self: argparse_namespace(limit=400, since_days=7, fail_on_gap=True),
    )

    assert audit.main() == 0
    output = capsys.readouterr().out
    assert "1 passing, 1 with a failing verdict" in output
    assert "FAILING  bbbbbbbbb" in output


def argparse_namespace(**kwargs: object) -> argparse.Namespace:
    return argparse.Namespace(**kwargs)


def _dispatch_git(repository: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repository, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _dispatch_commit(repository: Path, message: str) -> str:
    (repository / "file.txt").write_text(message, encoding="utf-8")
    _dispatch_git(repository, "add", "file.txt")
    _dispatch_git(repository, "commit", "-q", "-m", message)
    return _dispatch_git(repository, "rev-parse", "HEAD")


def test_range_enumeration_excludes_commits_the_pr_did_not_add(tmp_path: Path) -> None:
    """The mechanism, reproduced in a real repository rather than asserted as a string.

    `pull_request.commits` counts the branch when the event fired. A rebase that
    drops a commit already on main leaves that count larger than the window that
    landed, and `rev-list -n COUNT` then walks past the PR into commits earlier
    merges put there.

    Those commits are genuine ancestors of main and genuinely number COUNT, so
    the dispatcher's ancestry guard and a naive count assertion **both pass on a
    wrong enumeration**. That is why this is behavioural: no assertion about the
    workflow text can show that the two forms disagree.

    Latent in this repository -- no merged PR here has declared more commits
    than it landed -- but measured elsewhere in the estate: lotus-risk PR #270
    declared 4 and landed 3, and lotus-gateway PR #744 reached base.sha, where a
    commit being its own ancestor made the guard refuse the entire dispatch.
    """
    repository = tmp_path / "repo"
    repository.mkdir()
    _dispatch_git(repository, "init", "-q", "-b", "main")
    _dispatch_git(repository, "config", "user.email", "test@example.com")
    _dispatch_git(repository, "config", "user.name", "test")

    _dispatch_commit(repository, "root")
    earlier_pr_commit = _dispatch_commit(repository, "landed by an earlier PR")
    base_sha = earlier_pr_commit

    first = _dispatch_commit(repository, "this PR, revision 1")
    second = _dispatch_commit(repository, "this PR, revision 2")
    merge_sha = _dispatch_commit(repository, "this PR, revision 3")

    landed = [first, second, merge_sha]
    declared_count = len(landed) + 1  # a rebase dropped one already on main

    # Run the enumeration the workflow ACTUALLY ships, not a restatement of it.
    # A hand-written `rev-list --reverse` here would pass while the dispatcher
    # said something else entirely -- the test would be about the author's
    # understanding rather than about the shipped command.
    #
    # Arguments are extracted and run directly rather than through `bash -c`:
    # on a Windows developer machine `bash` resolves to WSL, which need not
    # exist, and a test that only runs in CI is a test that stops being read.
    dispatcher = (WORKFLOW_ROOT / "merged-pr-main-releasability.yml").read_text(encoding="utf-8")
    shipped = next(
        line.strip() for line in dispatcher.splitlines() if line.strip().startswith("revisions=")
    )
    inner = shipped[shipped.index("$(") + 2 : shipped.rindex(")")]
    arguments = shlex.split(
        inner.replace("$BASE_SHA", base_sha)
        .replace("$MERGE_COMMIT_SHA", merge_sha)
        .replace("$COMMIT_COUNT", str(declared_count))
    )
    assert arguments[0] == "git", f"the dispatcher no longer enumerates with git: {shipped}"
    by_range = _dispatch_git(repository, *arguments[1:]).splitlines()
    by_count = list(
        reversed(
            _dispatch_git(repository, "rev-list", "-n", str(declared_count), merge_sha).splitlines()
        )
    )

    assert by_range == landed, (
        "the enumeration the dispatcher ships must produce exactly what the PR added; "
        f"it produced {by_range}"
    )
    assert earlier_pr_commit in by_count, (
        "the count-bounded walk must reach the earlier PR's commit -- if it does not, "
        "this test no longer reproduces the defect it exists for"
    )
    assert earlier_pr_commit not in by_range
    assert len(by_count) > len(by_range)

    # Both guards the dispatcher relies on pass on the wrong enumeration, which
    # is why neither could have caught this.
    assert len(by_count) == declared_count, "a count assertion accepts the wrong window"
    for revision in by_count:
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", revision, merge_sha],
            cwd=repository,
            capture_output=True,
            check=False,  # the exit status IS the assertion here
        )
        assert ancestry.returncode == 0, "an ancestry check also accepts the wrong window"
