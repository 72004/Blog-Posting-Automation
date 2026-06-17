from __future__ import annotations

import base64

from openai import OpenAI


class OpenAIService:
    def __init__(self, api_key: str, model: str) -> None:
        self.client = OpenAI(api_key=api_key)
        self.model = model

    def generate_text(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt,
        )
        return response.output_text

    def generate_image(self, prompt: str, size: str = "1024x1024") -> bytes:
        response = self.client.images.generate(
            model="gpt-image-1",
            prompt=prompt,
            size=size,
        )
        image_b64 = response.data[0].b64_json
        if image_b64 is None:
            raise RuntimeError("OpenAI image response did not include image data")
        return base64.b64decode(image_b64)