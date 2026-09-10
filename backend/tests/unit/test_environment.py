from __future__ import annotations

import os
from pathlib import Path


def test_when_local_env_file_exists_then_loader_exports_its_values_without_overwriting_shell_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from app.environment import load_local_environment

    env_file = tmp_path / ".env"
    env_file.write_text("DEEPSEEK_API_KEY=from-file\nDEEPSEEK_MODEL=deepseek-v4-pro\n")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-shell")
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)

    load_local_environment(env_file)

    assert os.environ["DEEPSEEK_API_KEY"] == "from-shell"
    assert os.environ["DEEPSEEK_MODEL"] == "deepseek-v4-pro"
