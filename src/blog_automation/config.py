from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def _clean_env_value(value: str) -> str:
    return value.strip().strip('"').strip("'")


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    wordpress_base_url: str
    wordpress_username: str
    wordpress_app_password: str
    blog_home_base_url: str
    blog_home_username: str
    blog_home_password: str
    google_sheets_credentials_path: str
    google_sheets_credentials_json: str
    google_sheet_id: str
    output_dir: Path
    max_research_results: int


def get_settings() -> Settings:
    output_dir = Path(os.getenv("OUTPUT_DIR", "output"))
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "logs").mkdir(parents=True, exist_ok=True)

    return Settings(
        openai_api_key=_clean_env_value(os.getenv("OPENAI_API_KEY", "")),
        openai_model=_clean_env_value(os.getenv("OPENAI_MODEL", "gpt-4.1-mini")),
        wordpress_base_url=_clean_env_value(os.getenv("WORDPRESS_BASE_URL", "")),
        wordpress_username=_clean_env_value(os.getenv("WORDPRESS_USERNAME", "")),
        wordpress_app_password=_clean_env_value(os.getenv("WORDPRESS_APP_PASSWORD", "")),
        blog_home_base_url=_clean_env_value(os.getenv("BLOG_HOME_URL", "")),
        blog_home_username=_clean_env_value(os.getenv("BLOG_HOME_USERNAME", "")),
        blog_home_password=_clean_env_value(os.getenv("BLOG_HOME_PASSWORD", "")),
        google_sheets_credentials_path=_clean_env_value(os.getenv("GOOGLE_SHEETS_CREDENTIALS_PATH", "")),
        google_sheets_credentials_json=os.getenv("GOOGLE_SHEETS_CREDENTIALS_JSON", ""),
        google_sheet_id=_clean_env_value(os.getenv("GOOGLE_SHEET_ID", "")),
        output_dir=output_dir,
        max_research_results=int(os.getenv("MAX_RESEARCH_RESULTS", "5")),
    )