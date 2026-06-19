from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from openai import OpenAI

from blog_automation.utils.time_utils import pakistan_now_iso


class OpenAIService:
    IMAGE_MODEL = "gpt-image-1-mini"

    def __init__(self, api_key: str, model: str, log_path: Path | None = None) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model
        self.log_path = log_path
        self.text_request_count = 0
        self.image_request_count = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.request_log_entries: list[dict] = []

    @property
    def request_count(self) -> int:
        return self.text_request_count + self.image_request_count

    @property
    def summary(self) -> dict:
        return {
            "total_requests": self.request_count,
            "text_requests": self.text_request_count,
            "image_requests": self.image_request_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
        }

    def _log_request(self, entry: dict) -> None:
        self.request_log_entries.append(entry)
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(entry) + "\n")

    def generate_text(self, prompt: str, tag: str = "text") -> str:
        start = time.time()
        status = "success"
        error_message = ""
        input_tokens = 0
        output_tokens = 0
        try:
            response = self.client.responses.create(model=self.model, input=prompt)
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            return response.output_text
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            self.text_request_count += 1
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self._log_request(
                {
                    "timestamp": pakistan_now_iso(),
                    "type": "text",
                    "tag": tag,
                    "model": self.model,
                    "prompt_chars": len(prompt),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "duration_seconds": round(time.time() - start, 2),
                    "status": status,
                    "error": error_message,
                }
            )

    def generate_image(self, prompt: str, size: str = "1024x1024", quality: str = "medium", tag: str = "image") -> bytes:
        start = time.time()
        status = "success"
        error_message = ""
        input_tokens = 0
        output_tokens = 0
        try:
            response = self.client.images.generate(
                model=self.IMAGE_MODEL,
                prompt=prompt,
                size=size,
                quality=quality,
            )
            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            image_b64 = response.data[0].b64_json
            if image_b64 is None:
                raise RuntimeError("OpenAI image response did not include image data")
            return base64.b64decode(image_b64)
        except Exception as exc:
            status = "error"
            error_message = str(exc)
            raise
        finally:
            self.image_request_count += 1
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self._log_request(
                {
                    "timestamp": pakistan_now_iso(),
                    "type": "image",
                    "tag": tag,
                    "model": self.IMAGE_MODEL,
                    "size": size,
                    "quality": quality,
                    "prompt_chars": len(prompt),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "duration_seconds": round(time.time() - start, 2),
                    "status": status,
                    "error": error_message,
                }
            )
