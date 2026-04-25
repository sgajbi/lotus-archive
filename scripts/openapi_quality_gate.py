from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from app.main import app  # noqa: E402


def main() -> None:
    spec = app.openapi()
    if "paths" not in spec or not spec["paths"]:
        raise SystemExit("OpenAPI gate failed: no paths defined")
    print("OpenAPI gate passed")


if __name__ == "__main__":
    main()
