import json
from pathlib import Path

from app.main import app


ROOT = Path(__file__).resolve().parents[2]


def test_lifecycle_decision_contract_matches_openapi_and_runtime_models() -> None:
    contract = json.loads(
        (
            ROOT
            / "contracts"
            / "idea-lifecycle-decisions"
            / "lotus-archive-idea-evidence-lifecycle-decision.v1.json"
        ).read_text(encoding="utf-8")
    )
    operation = app.openapi()["paths"]["/documents/{document_id}/idea-lifecycle-decisions"]["post"]

    assert contract["product_id"] == "lotus-archive:IdeaEvidenceLifecycleDecision:v1"
    assert contract["authentication"]["algorithm"] == "Ed25519"
    assert contract["authentication"]["decision_ttl_seconds"] == 300
    assert contract["decision_precedence"][0] == "LEGAL_HOLD"
    assert "IdeaLifecycleDecisionRequest" in str(operation["requestBody"])
    assert "IdeaLifecycleDecision" in str(operation["responses"]["201"])
    assert {"403", "409", "422"}.issubset(operation["responses"])


def test_lifecycle_decision_contract_keeps_disposal_authority_in_archive() -> None:
    contract = json.loads(
        (
            ROOT
            / "contracts"
            / "idea-lifecycle-decisions"
            / "lotus-archive-idea-evidence-lifecycle-decision.v1.json"
        ).read_text(encoding="utf-8")
    )

    assert contract["authority"]["purge_execution"] == "lotus-archive"
    assert any("disposal_authorized is always false" in item for item in contract["invariants"])
    assert contract["persistence"]["production_posture"].startswith("blocked")
