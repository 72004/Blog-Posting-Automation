from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote_plus

import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

_RETRYABLE_STATUSES = {408, 415, 429, 500, 502, 503, 504}


def _rewind_file_streams(retry_state) -> None:
    """Reset any file streams in the 'files' kwarg so a retry re-sends full content
    instead of an empty body (the first attempt leaves the stream at EOF)."""
    files = (retry_state.kwargs or {}).get("files")
    if not files:
        return
    for value in files.values():
        stream = value[1] if isinstance(value, tuple) else value
        if hasattr(stream, "seek"):
            try:
                stream.seek(0)
            except (OSError, ValueError):
                pass


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, requests.HTTPError):
        return getattr(getattr(exc, "response", None), "status_code", None) in _RETRYABLE_STATUSES
    # Connection/SSL/timeout drops (e.g. a proxy silently closing a reused
    # keep-alive connection) are transient network failures, not HTTP responses.
    return isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))


_wordpress_retry = retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    before=_rewind_file_streams,
    reraise=True,
)


@dataclass
class WordPressConfig:
    base_url: str
    username: str
    app_password: str

    def __post_init__(self) -> None:
        # Strip spaces from app password (WordPress generates them with spaces)
        self.app_password = self.app_password.replace(" ", "")
        self.base_url = self.base_url.rstrip("/")

        missing = [f for f, v in [("base_url", self.base_url), ("username", self.username), ("app_password", self.app_password)] if not v]
        if missing:
            raise ValueError(f"WordPressConfig is missing required fields: {', '.join(missing)}")


class WordPressService:
    def __init__(self, config: WordPressConfig) -> None:
        self.config = config
        token = f"{config.username}:{config.app_password}".encode("utf-8")
        self.auth_header = {
            "Authorization": f"Basic {base64.b64encode(token).decode('utf-8')}"
        }
        self.session = requests.Session()
        # WAF/security plugins on some hosts flag the default python-requests
        # User-Agent as bot traffic and block/miscache the request. A normal
        # browser UA avoids that.
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                )
            }
        )

    def _raise_wordpress_error(self, response: requests.Response) -> None:
        detail = response.text.strip()
        status = response.status_code

        if status == 401:
            raise requests.HTTPError(
                f"401 Unauthorized: WordPress rejected your credentials.\n"
                f"  → Check that your Application Password is correct (WP Admin → Users → Profile → Application Passwords).\n"
                f"  → Ensure the username is your WordPress login username, not your email.\n"
                f"  → Make sure Application Passwords are not disabled in wp-config.php.\n"
                f"  → Raw response: {detail}",
                response=response,
            )
        if status == 403:
            raise requests.HTTPError(
                f"403 Forbidden: Your account lacks permission for this action.\n"
                f"  → Ensure the user has the 'Author' role or higher.\n"
                f"  → Raw response: {detail}",
                response=response,
            )

        if detail:
            raise requests.HTTPError(
                f"{status} {response.reason}: {detail}", response=response
            )
        response.raise_for_status()

    @_wordpress_retry
    def _post(self, url: str, **kwargs: object) -> requests.Response:
        extra_headers = kwargs.pop("headers", {})
        timeout = kwargs.pop("timeout", 60)
        response = self.session.post(
            url,
            headers={**self.auth_header, **extra_headers},
            timeout=timeout,
            **kwargs,
        )
        if not response.ok:
            self._raise_wordpress_error(response)
        return response

    def verify_account(self) -> dict:
        """Verify that the configured credentials are valid."""
        users_endpoint = f"{self.config.base_url}/wp-json/wp/v2/users/me"
        logger.debug("Verifying WordPress account at %s (user: %s)", users_endpoint, self.config.username)
        response = self._get(users_endpoint, timeout=30)
        data = response.json()
        logger.info("WordPress account verified: %s (id=%s)", data.get("name"), data.get("id"))
        return data

    @_wordpress_retry
    def _get(self, url: str, **kwargs: object) -> requests.Response:
        response = self.session.get(
            url,
            headers={**self.auth_header, **kwargs.pop("headers", {})},
            timeout=kwargs.pop("timeout", 60),
            **kwargs,
        )
        if not response.ok:
            self._raise_wordpress_error(response)
        return response

    def _find_tag_id(self, tag_name: str) -> int | None:
        tags_endpoint = f"{self.config.base_url}/wp-json/wp/v2/tags"
        search_url = f"{tags_endpoint}?search={quote_plus(tag_name)}&per_page=100"
        response = self._get(search_url, timeout=30)
        for tag in response.json():
            if str(tag.get("name", "")).strip().lower() == tag_name.strip().lower():
                return int(tag["id"])
            if str(tag.get("slug", "")).strip().lower() == tag_name.strip().lower().replace(" ", "-"):
                return int(tag["id"])
        return None

    def _get_or_create_tag_id(self, tag_name: str) -> int:
        existing_id = self._find_tag_id(tag_name)
        if existing_id is not None:
            return existing_id

        tags_endpoint = f"{self.config.base_url}/wp-json/wp/v2/tags"
        response = self._post(
            tags_endpoint,
            headers={"Content-Type": "application/json"},
            json={"name": tag_name},
            timeout=30,
        )
        return int(response.json()["id"])

    def resolve_tag_ids(self, tag_names: list[str]) -> list[int]:
        tag_ids: list[int] = []
        for tag_name in tag_names:
            cleaned_tag = tag_name.strip()
            if not cleaned_tag:
                continue
            tag_ids.append(self._get_or_create_tag_id(cleaned_tag))
        return tag_ids

    def upload_media(self, image_path: str, alt_text: str = "") -> dict:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {image_path}")

        media_endpoint = f"{self.config.base_url}/wp-json/wp/v2/media"

        with path.open("rb") as image_file:
            response = self._post(
                media_endpoint,
                headers={"Connection": "close"},
                files={"file": (path.name, image_file, "image/png")},
                timeout=120,
            )

        payload = response.json()
        if alt_text:
            self.update_media_alt_text(int(payload["id"]), alt_text)
        return payload

    def update_media_alt_text(self, media_id: int, alt_text: str) -> None:
        media_endpoint = f"{self.config.base_url}/wp-json/wp/v2/media/{media_id}"
        self._post(
            media_endpoint,
            headers={"Content-Type": "application/json"},
            json={"alt_text": alt_text},
            timeout=30,
        )

    def create_draft_post(
        self,
        title: str,
        content: str,
        meta_description: str,
        tags: list[str],
        categories: list[str],
        featured_media_id: int | None = None,
    ) -> dict:
        tag_ids = self.resolve_tag_ids(tags)
        post_endpoint = f"{self.config.base_url}/wp-json/wp/v2/posts"
        response = self._post(
            post_endpoint,
            headers={"Content-Type": "application/json"},
            json={
                "title": title,
                "content": content,
                "excerpt": meta_description,
                "status": "draft",
                "featured_media": featured_media_id or 0,
                "tags": tag_ids,
                "categories": categories,
            },
            timeout=60,
        )
        return response.json()