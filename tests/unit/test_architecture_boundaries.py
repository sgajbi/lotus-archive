import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_archive_service_does_not_import_api_models() -> None:
    tree = ast.parse((ROOT / "src" / "app" / "archive" / "service.py").read_text())

    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }

    assert "app.archive.api_models" not in imported_modules
