from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_local_environment(env_file: Path | None = None) -> None:
    """Load the backend's local .env file without replacing shell settings."""
    load_dotenv(env_file or Path(__file__).resolve().parent.parent / ".env", override=False)
