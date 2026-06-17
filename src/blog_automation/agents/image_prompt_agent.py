from __future__ import annotations

from blog_automation.models.workflow import BlogDraft, ImagePlan, SeoOutline, WorkflowInput
from blog_automation.services.openai_service import OpenAIService


class ImagePromptAgent:
    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def run(self, workflow_input: WorkflowInput, seo: SeoOutline, blog: BlogDraft) -> ImagePlan:
        cover_prompt = (
            f"Create a high quality cover image prompt for a blog article about {workflow_input.topic}. "
            f"Audience: {workflow_input.audience}. Style: professional, elegant, realistic, editorial. "
            f"Return only the image prompt sentence."
        )
        cover_image_prompt = self.openai_service.generate_text(cover_prompt).strip()

        section_prompts: list[str] = []
        alt_texts: list[str] = []

        for section in blog.sections:
            prompt = (
                f"Create a concise image prompt based only on this section content: "
                f"{section.content}. Topic: {workflow_input.topic}. "
                f"Style: professional, elegant, realistic photography. "
                f"Return only the image prompt sentence."
            )
            section_prompt = self.openai_service.generate_text(prompt).strip()
            section_prompts.append(section_prompt)
            alt_texts.append(f"{section.heading} illustration")

        return ImagePlan(
            cover_prompt=cover_image_prompt,
            section_prompts=section_prompts,
            alt_texts=alt_texts,
        )