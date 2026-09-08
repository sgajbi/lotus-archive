"""Resolve the PostgreSQL DSN for proofs that only a database can give.

The concurrency and durability proofs here are not convenience tests that
happen to use PostgreSQL. They assert behaviour the in-memory double **cannot**
exhibit: mutual exclusion between writers is decided by `UPDATE ... WHERE ...
RETURNING` against one row, and single-threaded Python cannot demonstrate it.

So a missing database is two different situations, and conflating them is how
these tests spent their whole existence skipping:

* On a developer machine with no database, skipping is right. The proof is
  unavailable, and saying so is honest.
* In a lane that exists to run the proof, skipping is a **false pass**. The
  gate reports success while the thing it gates was never evaluated -- the same
  shape as a gate that cannot fail.

`LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF=1` distinguishes them. CI sets it, so an
unreachable database fails the lane instead of quietly reducing it to nothing.
"""

from __future__ import annotations

import os

import pytest

DATABASE_URL_VARIABLE = "LOTUS_ARCHIVE_TEST_DATABASE_URL"
REQUIRED_VARIABLE = "LOTUS_ARCHIVE_REQUIRE_DATABASE_PROOF"


def database_proof_is_required() -> bool:
    return os.getenv(REQUIRED_VARIABLE, "") == "1"


def required_database_url() -> str:
    """The DSN, or a failure -- never a silent skip in a lane that requires it."""
    url = os.getenv(DATABASE_URL_VARIABLE, "")
    if url:
        return url
    if database_proof_is_required():
        raise RuntimeError(
            f"{REQUIRED_VARIABLE}=1 requires {DATABASE_URL_VARIABLE}, and it is unset. "
            "This lane exists to run the PostgreSQL proof; skipping it would report a "
            "pass for an assertion that was never evaluated."
        )
    # `allow_module_level` because two of the callers resolve the DSN at import
    # time, and a bare `pytest.skip()` outside a test is a collection ERROR
    # rather than a skip. That error broke `make test-pyramid-gate`, which only
    # collects -- so the lane that counts tests failed while every lane that
    # runs them was fine. Harmless from inside a fixture, which is how the
    # overlap suite calls it.
    pytest.skip(
        f"{DATABASE_URL_VARIABLE} is unset, so the PostgreSQL proof cannot run. "
        f"Set {REQUIRED_VARIABLE}=1 to make its absence a failure instead.",
        allow_module_level=True,
    )
