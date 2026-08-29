"""Assert the runtime image's installed distributions match the declared boundary.

Runs INSIDE the container under inspection (docker run --entrypoint python <image> this-script).
One script serves both lanes - the PR merge gate runs it against the locally built image, and
Main Releasability runs it against the pushed release digest before signing - so the two checks
cannot drift apart (issue #89).

The check is deliberately CVE-independent: a reintroduced installer fails here immediately,
whether or not a vulnerability database has an entry for it yet.
"""

from __future__ import annotations

import importlib.metadata as metadata

EXPECTED_DISTRIBUTIONS = {"cryptography": "50.0.0"}
FORBIDDEN_DISTRIBUTIONS = {"pip", "msgpack", "setuptools", "wheel"}


def main() -> None:
    installed = {
        distribution.metadata["Name"].lower(): distribution.version
        for distribution in metadata.distributions()
    }
    mismatches = {
        name: {"expected": version, "actual": installed.get(name)}
        for name, version in EXPECTED_DISTRIBUTIONS.items()
        if installed.get(name) != version
    }
    unexpected = sorted(FORBIDDEN_DISTRIBUTIONS & installed.keys())
    if mismatches or unexpected:
        raise SystemExit(
            f"Runtime dependency boundary violation: mismatches={mismatches}, "
            f"unexpected={unexpected}"
        )
    try:
        import pip
    except ModuleNotFoundError:
        pass
    else:
        raise SystemExit(f"Runtime package installer must be absent: {pip.__file__}")
    print("Runtime dependency boundary verified.")


if __name__ == "__main__":
    main()
