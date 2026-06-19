from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import gspread
from google.oauth2.service_account import Credentials

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

REQUEST_LOG_HEADERS = [
    "timestamp",
    "type",
    "tag",
    "model",
    "size",
    "quality",
    "prompt_chars",
    "input_tokens",
    "output_tokens",
    "duration_seconds",
    "status",
    "error",
]
RUN_LOG_HEADERS = [
    "timestamp",
    "topic",
    "topic_slug",
    "dry_run",
    "wordpress_post_url",
    "total_requests",
    "text_requests",
    "image_requests",
    "total_input_tokens",
    "total_output_tokens",
]


class GoogleSheetsService:
    """Mirrors openai_requests.jsonl / runs.jsonl rows into a Google Sheet.

    Failures here are logged and swallowed rather than raised, since the local
    JSONL files are the source of truth and a Sheets outage shouldn't break a run.
    """

    def __init__(self, sheet_id: str, credentials_path: str = "", credentials_json: str = "") -> None:
        self.sheet_id = sheet_id
        self.credentials_path = credentials_path
        self.credentials_json = credentials_json
        self._client: gspread.Client | None = None

    @property
    def is_configured(self) -> bool:
        if not self.sheet_id:
            return False
        if self.credentials_json.strip():
            return True
        return bool(self.credentials_path and Path(self.credentials_path).exists())

    def _get_client(self) -> gspread.Client:
        if self._client is None:
            if self.credentials_json.strip():
                # Cloud deployments (e.g. Streamlit Cloud) pass the key as a secret string
                # since there's no local file to point at.
                info = json.loads(self.credentials_json)
                credentials = Credentials.from_service_account_info(info, scopes=SCOPES)
            else:
                credentials = Credentials.from_service_account_file(self.credentials_path, scopes=SCOPES)
            self._client = gspread.authorize(credentials)
        return self._client

    def _get_worksheet(self, worksheet_name: str, headers: list[str]) -> gspread.Worksheet:
        spreadsheet = self._get_client().open_by_key(self.sheet_id)
        try:
            worksheet = spreadsheet.worksheet(worksheet_name)
        except gspread.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=len(headers))
            worksheet.append_row(headers)
            return worksheet
        if not worksheet.row_values(1):
            worksheet.append_row(headers)
        return worksheet

    def append_request_rows(self, entries: list[dict[str, Any]]) -> None:
        if not self.is_configured or not entries:
            return
        try:
            worksheet = self._get_worksheet("openai_requests", REQUEST_LOG_HEADERS)
            rows = [[str(entry.get(key, "")) for key in REQUEST_LOG_HEADERS] for entry in entries]
            worksheet.append_rows(rows, value_input_option="RAW")
        except Exception:
            logger.exception("Failed to sync request log rows to Google Sheets")

    def append_run_row(self, entry: dict[str, Any]) -> None:
        if not self.is_configured:
            return
        try:
            worksheet = self._get_worksheet("runs", RUN_LOG_HEADERS)
            row = [str(entry.get(key, "")) for key in RUN_LOG_HEADERS]
            worksheet.append_row(row, value_input_option="RAW")
        except Exception:
            logger.exception("Failed to sync run summary row to Google Sheets")
