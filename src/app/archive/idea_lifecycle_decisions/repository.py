from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Protocol

from app.archive.idea_lifecycle_decisions.models import IdeaLifecycleDecision


class LifecycleDecisionConflictError(ValueError):
    pass


class IdeaLifecycleDecisionRepository(Protocol):
    def get(self, idempotency_key: str) -> tuple[str, IdeaLifecycleDecision] | None: ...

    def save(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        decision: IdeaLifecycleDecision,
    ) -> IdeaLifecycleDecision: ...


class SqliteIdeaLifecycleDecisionRepository:
    def __init__(self, database_path: Path | str) -> None:
        self._database_path = Path(database_path)
        self._ensure_schema()

    def get(self, idempotency_key: str) -> tuple[str, IdeaLifecycleDecision] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT request_fingerprint, decision_json FROM idea_lifecycle_decision "
                "WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return str(row["request_fingerprint"]), IdeaLifecycleDecision.model_validate_json(
            row["decision_json"]
        )

    def save(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        decision: IdeaLifecycleDecision,
    ) -> IdeaLifecycleDecision:
        with self._connect() as connection:
            try:
                connection.execute(
                    "INSERT INTO idea_lifecycle_decision "
                    "(idempotency_key, request_fingerprint, decision_json) VALUES (?, ?, ?)",
                    (idempotency_key, request_fingerprint, decision.model_dump_json()),
                )
            except sqlite3.IntegrityError as exc:
                existing = self.get(idempotency_key)
                if existing and existing[0] == request_fingerprint:
                    return existing[1]
                raise LifecycleDecisionConflictError(
                    "idempotency key was reused with different lifecycle decision input"
                ) from exc
        return decision

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._database_path != Path(":memory:"):
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS idea_lifecycle_decision ("
                "idempotency_key TEXT PRIMARY KEY, "
                "request_fingerprint TEXT NOT NULL, "
                "decision_json TEXT NOT NULL)"
            )
