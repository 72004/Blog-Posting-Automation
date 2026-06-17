from __future__ import annotations

from blog_automation.agents.image_prompt_agent import ImagePromptAgent
from blog_automation.agents.research_agent import ResearchAgent
from blog_automation.agents.seo_outline_agent import SeoOutlineAgent
from blog_automation.agents.writer_agent import BlogWriterAgent
from blog_automation.config import Settings
from blog_automation.models.workflow import WorkflowInput, WorkflowResult
from blog_automation.services.image_service import ImageService
from blog_automation.services.openai_service import OpenAIService
from blog_automation.services.web_research_service import WebResearchService
from blog_automation.services.wordpress_service import WordPressConfig, WordPressService
from blog_automation.utils.file_utils import write_text_file
from blog_automation.utils.html_utils import normalize_paragraph
from blog_automation.utils.text_utils import slugify


class BlogAutomationOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.openai_service = OpenAIService(settings.openai_api_key, settings.openai_model)
        self.research_service = WebResearchService(settings.max_research_results)
        self.image_service = ImageService(settings.output_dir)
        self.wordpress_service = WordPressService(
            WordPressConfig(
                base_url=settings.wordpress_base_url,
                username=settings.wordpress_username,
                app_password=settings.wordpress_app_password,
            )
        )
        self.research_agent = ResearchAgent(self.research_service)
        self.seo_agent = SeoOutlineAgent(self.openai_service)
        self.writer_agent = BlogWriterAgent(self.openai_service)
        self.image_prompt_agent = ImagePromptAgent(self.openai_service)

    def run(self, workflow_input: WorkflowInput, dry_run: bool = False) -> WorkflowResult:
        research = self.research_agent.run(workflow_input)
        seo = self.seo_agent.run(workflow_input, research)
        blog = self.writer_agent.run(workflow_input, research, seo)
        images = self.image_prompt_agent.run(workflow_input, seo, blog)

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
            image_bytes = self.openai_service.generate_image(prompt, size="1536x1024")
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

        return WorkflowResult(
            input=workflow_input,
            research=research,
            seo=seo,
            blog=blog,
            images=images,
            media=[],
            wordpress_post_id=post_id,
            wordpress_post_url=post_url,
        )