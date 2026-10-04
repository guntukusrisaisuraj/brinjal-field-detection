"""Application environment loading helpers."""
from pathlib import Path

from dotenv import load_dotenv


def load_backend_environment() -> bool:
    """Load the backend .env without overriding variables set by the process."""
    dotenv_path = Path(__file__).resolve().parents[1] / ".env"
    return load_dotenv(dotenv_path=dotenv_path, override=False)
