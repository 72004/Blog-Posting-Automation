import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

from blog_automation.services.wordpress_service import WordPressService, WordPressConfig

config = WordPressConfig(
    base_url=os.environ["BLOG_HOME_URL"],
    username=os.environ["BLOG_HOME_USERNAME"],
    app_password=os.environ["BLOG_HOME_PASSWORD"],
)
svc = WordPressService(config)

from PIL import Image

tmp_img = Path(__file__).parent / "_verify_upload_image.png"
Image.new("RGB", (4, 4), color=(0, 128, 255)).save(tmp_img)

print("=== upload_media() (previously threw SSLEOFError here) ===")
media = svc.upload_media(str(tmp_img), alt_text="diagnostic alt text")
print("OK -> media id:", media.get("id"), "source_url:", media.get("source_url"))
print("CLEANUP", media["id"])
