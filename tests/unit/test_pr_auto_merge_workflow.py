from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_auto_merge_uses_repository_approved_rebase_strategy() -> None:
    workflow = (ROOT / ".github/workflows/pr-auto-merge.yml").read_text(encoding="utf-8")

    merge_command = next(line.strip() for line in workflow.splitlines() if "gh pr merge" in line)

    assert "--auto --rebase --delete-branch" in merge_command
    assert "--merge" not in merge_command
    assert "--squash" not in merge_command
    assert "Enable auto-merge queue (rebase)" in workflow
