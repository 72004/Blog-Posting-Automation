from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


class ImageService:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def save_image_bytes(self, image_bytes: bytes, filename: str, images_dir: Path) -> Path:
        images_dir.mkdir(parents=True, exist_ok=True)
        image_path = images_dir / filename
        image_path.write_bytes(image_bytes)
        return image_path

    def resize_image(self, image_path: Path, width: int, height: int) -> Path:
        with Image.open(image_path) as image:
            resized = ImageOps.fit(image.convert("RGB"), (width, height), Image.Resampling.LANCZOS)
            resized.save(image_path)
        return image_path