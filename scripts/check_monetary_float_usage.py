import sys
from pathlib import Path

MONETARY_HINTS = ("amount", "value", "price", "cost", "pnl", "market_value", "fx_rate")
ALLOWLIST = set()


def likely_monetary(line: str) -> bool:
    low = line.lower()
    return any(token in low for token in MONETARY_HINTS)


def main() -> int:
    violations: list[str] = []
    for path in Path("src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for idx, line in enumerate(text.splitlines(), start=1):
            if "float(" in line and likely_monetary(line) and f"{path}:{idx}" not in ALLOWLIST:
                violations.append(f"{path}:{idx}: monetary float usage detected")
    if violations:
        print("\\n".join(violations))
        return 1
    print("Monetary float guard passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
