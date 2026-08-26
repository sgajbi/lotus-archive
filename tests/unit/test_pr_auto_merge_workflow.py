from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_auto_merge_uses_repository_approved_rebase_strategy() -> None:
    workflow = (ROOT / ".github/workflows/pr-auto-merge.yml").read_text(encoding="utf-8")

    merge_command = next(line.strip() for line in workflow.splitlines() if "gh pr merge" in line)

    assert "--auto --rebase --delete-branch" in merge_command
    assert "--merge" not in merge_command
    assert "--squash" not in merge_command
    assert "Enable auto-merge queue (rebase)" in workflow


WORKFLOW_ROOT = ROOT / ".github/workflows"
GATEWAY_REFERENCE_NOTE = (
    "lotus-gateway is the reference implementation; divergence here reintroduces the ungated-main "
    "defect recorded in issue #80."
)


def test_auto_merge_uses_a_token_that_can_trigger_downstream_workflows() -> None:
    """GITHUB_TOKEN pushes do not trigger workflow runs.

    Under `github.token` an automated merge pushes to `main` without triggering
    `main-releasability.yml`, so the commit lands ungated. This repository has not been bitten
    only because its last merge was performed by a human (#80).
    """

    workflow = (WORKFLOW_ROOT / "pr-auto-merge.yml").read_text(encoding="utf-8")

    assert "secrets.LOTUS_AUTOMERGE_TOKEN" in workflow, GATEWAY_REFERENCE_NOTE
    assert "GH_TOKEN: ${{ github.token }}" not in workflow, GATEWAY_REFERENCE_NOTE


def test_auto_merge_warns_when_the_token_is_absent() -> None:
    """Named for what the guard does, not what it should do.

    The guard `exit 0`s, so `Queue Auto Merge` reports **success** whether it armed or skipped.
    That is the silent-success defect recorded on lotus-platform#710, and it is deliberately not
    fixed here: this workflow is byte-identical to lotus-gateway's, and a local improvement would
    cost that identity for a fix that belongs estate-wide.
    """

    workflow = (WORKFLOW_ROOT / "pr-auto-merge.yml").read_text(encoding="utf-8")

    assert 'if [ -z "$GH_TOKEN" ]; then' in workflow
    assert "::warning::LOTUS_AUTOMERGE_TOKEN is required" in workflow


def test_auto_merge_requests_no_more_permission_than_it_needs() -> None:
    workflow = (WORKFLOW_ROOT / "pr-auto-merge.yml").read_text(encoding="utf-8")

    assert "permissions:\n  contents: read\n" in workflow
    assert "contents: write" not in workflow
    assert "timeout-minutes:" in workflow


def test_a_dispatcher_exists_so_the_gate_does_not_depend_on_the_push_trigger() -> None:
    dispatcher_path = WORKFLOW_ROOT / "merged-pr-main-releasability.yml"

    assert dispatcher_path.is_file(), (
        "merged-pr-main-releasability.yml is the fallback that runs the gate when the merge push "
        "does not trigger it. " + GATEWAY_REFERENCE_NOTE
    )
    dispatcher = dispatcher_path.read_text(encoding="utf-8")
    assert "types: [closed]" in dispatcher
    assert "pull_request.merged == true" in dispatcher
    assert "gh workflow run main-releasability.yml" in dispatcher
    assert "expected_sha" in dispatcher


def test_main_releasability_validates_the_exact_dispatched_revision() -> None:
    workflow = (WORKFLOW_ROOT / "main-releasability.yml").read_text(encoding="utf-8")

    assert "expected_sha:" in workflow
    assert "exact-revision-assertion:" in workflow
    assert "does not match expected merged PR SHA" in workflow
    assert workflow.count("needs: [exact-revision-assertion]") >= 2


def test_main_releasability_is_dispatch_only() -> None:
    """A suppressed push trigger is silent; a failed dispatch is a visible failed run."""

    workflow = (WORKFLOW_ROOT / "main-releasability.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert 'branches: [ "main" ]' not in workflow


def test_main_releasability_concurrency_is_keyed_per_commit_not_per_branch() -> None:
    """A branch-keyed group lets a second merge cancel the first commit's in-flight gate.

    With `cancel-in-progress: true` the earlier commit is left with a *cancelled* run — neither
    pass nor fail — and nothing reports it. Third of the three paths to an ungated `main`.
    """

    workflow = (WORKFLOW_ROOT / "main-releasability.yml").read_text(encoding="utf-8")

    assert "group: ${{ github.workflow }}-${{ github.sha }}" in workflow
    assert "group: ${{ github.workflow }}-${{ github.ref }}" not in workflow


def test_release_verification_pins_the_identity_to_the_running_ref() -> None:
    """Dispatching against a tag changes the signing identity's ref.

    The gate signs the release image with a keyless OIDC identity whose SAN embeds the ref the
    workflow ran on. While the gate ran on `push` that was always `refs/heads/main`; dispatched
    against the immutable `main-releasability-<sha>` tag it is `refs/tags/...`, so a value pinned
    to `refs/heads/main` fails verification — which is what broke `19fbef3d` on `main`.

    The fix is *not* to widen the pattern. This workflow verifies an artifact **it just produced in
    this same run**, so the exact ref it is running on is precisely the ref that signed. Using
    `${GITHUB_REF}` is therefore stricter than the original literal, not looser: it admits exactly
    one identity and it is always the right one.
    """

    workflow = (WORKFLOW_ROOT / "main-releasability.yml").read_text(encoding="utf-8")

    identity_lines = [
        line.strip()
        for line in workflow.splitlines()
        if "workflows/main-releasability.yml@" in line
    ]
    assert identity_lines, "expected at least one signing-identity assertion"
    for line in identity_lines:
        assert line.endswith('@${GITHUB_REF}"'), (
            f"signing identity must track the running ref, found: {line}"
        )
        assert "refs/heads/main" not in line, (
            "a hard-coded ref breaks whenever the gate is dispatched rather than pushed"
        )

    # Regex matching would allow a prefix or wildcard to creep in; exact identity cannot.
    assert "--certificate-identity-regexp" not in workflow
    assert "--cert-identity-regex" not in workflow

    # The provenance source-ref must track the run too, or it contradicts the identity above.
    assert '--source-ref "${GITHUB_REF}"' in workflow
    assert '--source-ref "refs/heads/main"' not in workflow
