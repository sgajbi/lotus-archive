"""Runtime readiness reporting for the archive document service.

Lives beside the service rather than in runtime.py because runtime.py builds
the service (importing this the other way would be circular).
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveRuntimeReadiness:
    repository_ready: bool
    storage_ready: bool
    access_audit_ready: bool


def dependency_is_ready(check_ready: Callable[[], None]) -> bool:
    try:
        check_ready()
    except Exception:
        return False
    return True
