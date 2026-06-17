from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_local_compose_does_not_require_untracked_env_file() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))

    env_file = compose["services"]["lotus-archive"]["env_file"]

    assert env_file == [{"path": ".env", "required": False}]
