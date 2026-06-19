from __future__ import annotations

import json
import re
from pathlib import Path

from blog_automation.agents.content_agent import BlogContentAgent
from blog_automation.agents.research_agent import ResearchAgent
from blog_automation.config import Settings
from blog_automation.models.workflow import PinterestPin, WorkflowInput, WorkflowResult
from blog_automation.services.google_sheets_service import GoogleSheetsService
from blog_automation.services.image_service import ImageService
from blog_automation.services.openai_service import OpenAIService
from blog_automation.services.web_research_service import WebResearchService
from blog_automation.services.wordpress_service import WordPressConfig, WordPressService
from blog_automation.utils.file_utils import write_text_file
from blog_automation.utils.html_utils import normalize_paragraph
from blog_automation.utils.text_utils import slugify
from blog_automation.utils.time_utils import pakistan_now_iso

PINTEREST_PROMPT_TEMPLATES = [
    """Create a highly clickable Pinterest pin in vertical 2:3 ratio (1024x1536).

Topic: {KEYWORD}

Generate a stunning, high-quality photorealistic scene that clearly and directly visualizes the
topic '{KEYWORD}'. Choose whatever setting, subjects, and props are genuinely appropriate to this
exact topic (for example: a styled home interior for a home/decor topic, a person working at a
laptop in a cozy home setting for a remote-work or career topic, a relevant real-world scene for
any other topic) — the scene must be obviously and unmistakably connected to what '{KEYWORD}' is
actually about, never defaulted to an unrelated subject regardless of the topic.

Style:
- Pinterest viral aesthetic
- Premium editorial photography appropriate to the topic
- Natural, flattering lighting suited to the scene and topic — not forced into any one color
  temperature; could be warm, cool, neutral, or vibrant depending on what actually fits the topic
- Polished, upscale atmosphere
- Professional styling
- Rich textures
- Premium editorial magazine quality
- Ultra realistic
- Photorealistic

Composition:
- One hero scene that visually represents the topic
- Strong visual depth
- Professional staging
- Premium, relevant props and setting details appropriate to the topic
- Leave ample central space for title design
- The headline must be the single most visually dominant element on the entire pin — very large,
  bold, and the first thing the eye is drawn to, more prominent than any other text or detail

Typography & Color System:
Analyze the dominant colors and brightness of the scene.

Automatically create:
- One single premium title badge/panel large enough to fully contain both the number and the
  rest of the headline text together as one unit — the number must sit inside this same box, not
  floating outside or above it
- Main text color
- Accent text color

Rules:
- Use colors sampled from the scene's own real elements (its setting, objects, materials, and
  lighting).
- Ensure strong contrast and readability.
- If the scene is dark, use light typography.
- If the scene is light, use darker typography.
- Use elegant luxury color harmony.
- Pinterest mobile-first readability.
- The title badge/panel background should be semi-transparent (roughly 60-70% opacity), not a
  fully solid block, so the photo is still subtly visible behind the text while the text itself
  stays fully legible and high-contrast.

Text Overlay (two-line headline, centered, both lines inside the same title badge/panel):

Line 1 — large, bold, centered, standalone by itself on its own line, inside the title box:
"{NUMBER}"

Line 2 — directly below line 1, still inside the same title box, smaller than line 1 but still
bold and legible:
"{TITLE_REST}"

Typography:
- Huge bold editorial font
- Line 1 (the number) must be rendered significantly larger and bolder than line 2 — it is the
  single most eye-catching element, the way a magazine cover spotlights a big number, centered at
  the top of the title area
- Use a stylish, sophisticated font pairing — a refined bold serif or display font for line 2,
  mixed with one elegant handwritten or script-style accent word for emphasis, the same way a
  premium magazine cover or boutique brand treats its title
- Add a small decorative touch around the title — a thin accent line, subtle flourish, small
  ornament, or delicate underline — so the text feels custom-designed and elegant rather than
  plain default text
- Magazine cover quality
- Premium Pinterest design

The final image should look like a viral Pinterest pin created by a professional Pinterest content publisher.""",
    """Create a viral Pinterest pin in vertical 2:3 ratio (1024x1536).

Topic: {KEYWORD}

Generate four different high-quality, photorealistic scenes that each visually represent a
different aspect of the topic '{KEYWORD}'. Choose whatever settings, subjects, and props are
genuinely appropriate to this exact topic — the scenes must be obviously and unmistakably
connected to what '{KEYWORD}' is actually about, never defaulted to an unrelated subject
regardless of the topic.

Layout:
- The image must be divided into a strict 2x2 grid: exactly 2 columns and 2 rows, 4 equal
  quadrants total
- Each of the 4 quadrants must contain one complete, distinct photo — 4 separate photos in
  total, not 1 or 2 photos repeated or stretched across multiple quadrants
- Each of the 4 photos must show a clearly different variation, camera angle, or styling so all
  four are visually distinguishable from one another at a glance
- Thin elegant dividers (a few pixels wide) separate the 4 quadrants so each photo's edges are
  clearly visible
- High-end editorial photography appropriate to the topic
- Polished, premium aesthetic
- Natural, flattering lighting suited to the scenes and topic — not forced into any one color
  temperature; could be warm, cool, neutral, or vibrant depending on what actually fits the topic
- Photorealistic quality

Centerpiece:
Create a large, ornate central badge for the title — a decorative scalloped or flower-shaped
frame (not a plain rectangle or circle), in a light cream or white tone with a thin elegant
accent-color border (chosen to complement this specific collage's own colors, not necessarily
gold) and a few small sparkle/star accents, positioned over the middle of the collage like a
premium label.

Typography & Color System:

Analyze the colors of all four images.

Automatically create:
- Title badge color
- Primary text color
- Accent typography color

Rules:
- Colors must harmonize with the photos.
- Strong readability is required.
- Use premium luxury color combinations.
- Sample tones from the photos' own real elements (their settings, objects, materials, and
  lighting).
- The badge should feel custom-designed for this exact collage.
- Inside the badge, render the leading number ("{NUMBER}") large and bold at the very top — the
  single most prominent element in the badge, larger than the words below it.

Text Overlay (only the title text appears in the image — no subheadline or any other extra text):

Headline:
"{FULL_TITLE}"

Typography:
- Bold serif or bold sans-serif caps for the headline words inside the badge — the way a premium
  product label is designed
- Large bold white or contrasting font
- Luxury Pinterest aesthetic
- Editorial magazine design

Result should resemble a top-performing Pinterest collage with very high click-through rate.""",
    """Create a premium Pinterest pin in vertical 2:3 ratio (1024x1536).

Topic: {KEYWORD}

Generate a high-quality, photorealistic scene that clearly visualizes the topic '{KEYWORD}'.
Choose whatever setting, subjects, and props are genuinely appropriate to this exact topic — the
scene must be obviously and unmistakably connected to what '{KEYWORD}' is actually about, never
defaulted to an unrelated subject regardless of the topic.

Style:
- Premium editorial magazine quality
- Premium editorial photography appropriate to the topic
- Natural, flattering lighting suited to the scene and topic — not forced into any one color
  temperature; could be warm, cool, neutral, or vibrant depending on what actually fits the topic
- Rich textures
- Ultra realistic
- Sophisticated styling

Composition:
- One full-bleed hero scene fills the entire frame top to bottom — the same approach as the
  single-scene pin — not a separate non-photo title card region sitting above the photo
- The headline is overlaid directly on top of the photo near the top of the frame, blended into
  the scene exactly the same way as the single-scene pin (a semi-transparent gradient or panel
  behind the text, not a solid separate card that pushes the photo down)
- A bold 'READ MORE' call-to-action badge/button is overlaid in the lower portion of the photo,
  positioned with comfortable margin above the very bottom edge (not flush against it, roughly
  10-15% up from the bottom of the frame), with a contrasting background color and a small arrow
  icon, styled like a clickable button
- Strong visual hierarchy
- Clean modern Pinterest layout
- High-end publishing aesthetic

Typography & Color System:

Analyze the scene's dominant palette.

Automatically generate:
- Semi-transparent title overlay/gradient color (not a solid separate card) — the same treatment
  as the single-scene pin
- Primary typography color
- Accent typography color
- 'READ MORE' badge color, contrasting against the area behind it

Requirements:
- The title text area must be a semi-transparent gradient or panel overlaid directly on the photo
  (roughly 60-70% opacity), blended into the scene — not a solid separate card sitting above the
  photo. This must look and feel identical to the single-scene pin's title treatment.
- Colors should be derived from the scene.
- Luxury aesthetic.
- Maximum readability.
- Harmonized with the scene's own real elements and lighting.
- Looks professionally designed, not templated.

Text Overlay (two-line headline at the top, formatted the same way as the single-scene pin — the
only text in this image is the title and the call-to-action badge below, no subheadline or any
other extra text):

Line 1 — large, bold, centered, standalone by itself on its own line, at the very top:
"{NUMBER}"

Line 2 — directly below line 1, smaller than line 1 but still bold and legible:
"{TITLE_REST}"

Call-to-action badge (in the lower portion, slightly up from the bottom edge):
"READ MORE"

Typography:
- Huge bold editorial font
- Line 1 (the number) must be rendered significantly larger and bolder than line 2 — it is the
  single most eye-catching element, the way a magazine cover spotlights a big number, centered at
  the top of the title area
- Use a stylish, sophisticated font pairing — a refined bold serif or display font for line 2,
  mixed with one elegant handwritten or script-style accent word for emphasis, the same way a
  premium magazine cover or boutique brand treats its title
- Add a small decorative touch around the title — a thin accent line, subtle flourish, small
  ornament, or delicate underline — so the text feels custom-designed and elegant rather than
  plain default text
- Luxury editorial design with strong visual richness, not minimal or generic
- Elegant accent styling
- Pinterest mobile optimized

Final result should look like a premium publisher's Pinterest pin with extremely high engagement potential.""",
]

PINTEREST_EDGE_SAFETY_NOTE = (
    " Every word of every text element must be fully visible with clear empty margin on all four "
    "edges of the canvas — no text may touch or extend past any edge."
)
PINTEREST_DYNAMIC_COLOR_NOTE = (
    " The badge and typography colors must be uniquely sampled from this specific photo's actual "
    "visible colors (its real objects, materials, and lighting tones) — do not default to a "
    "repeated, generic, or stock color scheme; let the palette genuinely vary based on what is "
    "actually in this particular scene. In particular, do not default to brown, gold, or other "
    "warm-toned color schemes out of habit — the palette should be whatever genuinely fits this "
    "topic and scene, which could just as easily be cool tones, blues, greens, neutrals, or "
    "vibrant colors."
)


class BlogAutomationOrchestrator:
    def __init__(self, settings: Settings, wordpress_config: WordPressConfig | None = None) -> None:
        self.settings = settings
        self.openai_service = OpenAIService(
            settings.openai_api_key,
            settings.openai_model,
            log_path=settings.output_dir / "logs" / "openai_requests.jsonl",
        )
        self.research_service = WebResearchService(settings.max_research_results)
        self.image_service = ImageService(settings.output_dir)
        self.wordpress_service = WordPressService(
            wordpress_config
            or WordPressConfig(
                base_url=settings.wordpress_base_url,
                username=settings.wordpress_username,
                app_password=settings.wordpress_app_password,
            )
        )
        self.research_agent = ResearchAgent(self.research_service)
        self.content_agent = BlogContentAgent(self.openai_service)
        self.google_sheets_service = GoogleSheetsService(
            settings.google_sheet_id,
            credentials_path=settings.google_sheets_credentials_path,
            credentials_json=settings.google_sheets_credentials_json,
        )

    def run(
        self, workflow_input: WorkflowInput, dry_run: bool = False, include_pinterest_images: bool = True
    ) -> WorkflowResult:
        research = self.research_agent.run(workflow_input)
        seo, blog, images, pinterest_pins = self.content_agent.run(workflow_input, research)

        if not dry_run:
            self.wordpress_service.verify_account()

        topic_slug = slugify(seo.blog_title or workflow_input.topic)
        topic_dir = self.settings.output_dir / topic_slug
        images_dir = topic_dir / "images"

        draft_filename = f"{topic_slug}.html"
        draft_path = topic_dir / draft_filename
        write_text_file(draft_path, blog.html_content)

        media_items = []

        image_prompts = images.section_prompts
        alt_texts = images.alt_texts[: len(image_prompts)]

        for index, prompt in enumerate(image_prompts):
            image_bytes = self.openai_service.generate_image(prompt, size="1024x1024", tag="section_image")
            image_path = self.image_service.save_image_bytes(
                image_bytes, f"{topic_slug}_{index + 1}.png", images_dir
            )
            image_path = self.image_service.resize_image(image_path, 561, 374)
            if dry_run:
                media_items.append({"id": index + 1, "source_url": f"images/{image_path.name}"})
            else:
                media_items.append(
                    self.wordpress_service.upload_media(str(image_path), alt_text=alt_texts[index] if index < len(alt_texts) else "")
                )

        image_urls = [media_item.get("source_url", "") for media_item in media_items]
        html_parts: list[str] = [f"<h1>{seo.blog_title or workflow_input.topic}</h1>"]
        html_parts.append(f"<p>{normalize_paragraph(blog.intro)}</p>")

        for section_number, section in enumerate(blog.sections, start=1):
            image_index = section_number - 1
            html_parts.append(f"<h2>{section_number}. {section.heading}</h2>")
            if image_index < len(image_urls) and image_urls[image_index]:
                alt_text = images.alt_texts[image_index] if image_index < len(images.alt_texts) else section.heading
                html_parts.append(
                    f'<p style="text-align: center;"><img src="{image_urls[image_index]}" alt="{alt_text}" style="display: block; margin: 0 auto; max-width: 100%; height: auto;" /></p>'
                )
            html_parts.append(f"<p>{normalize_paragraph(section.content)}</p>")

        assembled_html = "\n".join(html_parts)
        write_text_file(draft_path, assembled_html)

        post_id = None
        post_url = ""
        if not dry_run:
            featured_media_id = int(media_items[0]["id"]) if media_items else None
            post = self.wordpress_service.create_draft_post(
                title=seo.blog_title or workflow_input.topic,
                content=assembled_html,
                meta_description=seo.meta_description,
                tags=seo.target_keywords,
                categories=[],
                featured_media_id=featured_media_id,
            )
            post_id = int(post["id"])
            post_url = post.get("link", "")

        if include_pinterest_images:
            self._generate_pinterest_images(workflow_input.topic, topic_slug, topic_dir, pinterest_pins)
        else:
            pinterest_pins = []

        runs_log_path = self.settings.output_dir / "logs" / "runs.jsonl"
        runs_log_path.parent.mkdir(parents=True, exist_ok=True)
        run_summary = {
            "timestamp": pakistan_now_iso(),
            "topic": workflow_input.topic,
            "topic_slug": topic_slug,
            "dry_run": dry_run,
            "wordpress_post_url": post_url,
            **self.openai_service.summary,
        }
        with runs_log_path.open("a", encoding="utf-8") as runs_log_file:
            runs_log_file.write(json.dumps(run_summary) + "\n")

        self.google_sheets_service.append_request_rows(self.openai_service.request_log_entries)
        self.google_sheets_service.append_run_row(run_summary)

        return WorkflowResult(
            input=workflow_input,
            research=research,
            seo=seo,
            blog=blog,
            images=images,
            media=[],
            pinterest_pins=pinterest_pins,
            wordpress_post_id=post_id,
            wordpress_post_url=post_url,
        )

    def _generate_pinterest_images(
        self, topic: str, topic_slug: str, topic_dir: Path, pinterest_pins: list[PinterestPin]
    ) -> None:
        pinterest_dir = topic_dir / "pinterest"
        number_match = re.match(r"^\s*(\d+)", topic)
        number = number_match.group(1) if number_match else ""
        keyword = re.sub(r"^\s*\d+\s*", "", topic).strip() or topic.strip()
        # Templates already append their own "Ideas" suffix in the headline, so strip a
        # trailing "Ideas" from the keyword to avoid "...Ideas Ideas" duplication.
        keyword = re.sub(r"\s+Ideas\s*$", "", keyword, flags=re.IGNORECASE).strip() or keyword

        for index, pin in enumerate(pinterest_pins):
            template = PINTEREST_PROMPT_TEMPLATES[index % len(PINTEREST_PROMPT_TEMPLATES)]

            # Render the actual generated pin title (no hashtags) in the image, instead of a
            # separately constructed phrase, so the image text matches the displayed title.
            clean_title = re.sub(r"\s{2,}", " ", re.sub(r"#\S+", "", pin.title)).strip()
            title_number_match = re.match(r"^\s*(\d+)\s*", clean_title)
            if title_number_match:
                title_number = title_number_match.group(1)
                title_rest = clean_title[title_number_match.end():].strip()
            else:
                title_number = number
                title_rest = clean_title or keyword
            full_title = clean_title or f"{number} {keyword}".strip()

            pin_prompt = template.replace("{KEYWORD}", keyword)
            pin_prompt = pin_prompt.replace("{NUMBER}", title_number)
            pin_prompt = pin_prompt.replace("{TITLE_REST}", title_rest)
            pin_prompt = pin_prompt.replace("{FULL_TITLE}", full_title)
            pin_prompt += PINTEREST_EDGE_SAFETY_NOTE
            pin_prompt += PINTEREST_DYNAMIC_COLOR_NOTE

            pin_image_bytes = self.openai_service.generate_image(
                pin_prompt, size="1024x1536", quality="medium", tag="pinterest_image"
            )
            pin_image_path = self.image_service.save_image_bytes(
                pin_image_bytes, f"{topic_slug}_pinterest_{index + 1}.png", pinterest_dir
            )
            pin.image_path = str(pin_image_path)

    def run_pinterest_only(self, workflow_input: WorkflowInput) -> list[PinterestPin]:
        """Generate just the Pinterest pins, skipping research, blog content, and WordPress.

        Used for the "Just Pinterest" generation mode.
        """
        pinterest_pins = self.content_agent.generate_pinterest_pins(workflow_input)
        topic_slug = slugify(workflow_input.topic)
        topic_dir = self.settings.output_dir / topic_slug
        self._generate_pinterest_images(workflow_input.topic, topic_slug, topic_dir, pinterest_pins)
        self.google_sheets_service.append_request_rows(self.openai_service.request_log_entries)
        return pinterest_pins