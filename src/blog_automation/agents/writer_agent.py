from __future__ import annotations

from blog_automation.models.workflow import BlogDraft, ResearchSummary, SectionDraft, SeoOutline, WorkflowInput
from blog_automation.services.openai_service import OpenAIService
from blog_automation.utils.html_utils import normalize_paragraph
from blog_automation.utils.text_utils import word_count


class BlogWriterAgent:
    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def run(self, workflow_input: WorkflowInput, research: ResearchSummary, seo: SeoOutline) -> BlogDraft:
        intro_prompt = (
            f"Write a short introduction of 45 to 60 words for an article titled '{seo.blog_title}'. "
            f"Audience: {workflow_input.audience}. Tone: {workflow_input.tone}."
        )
        intro = self.openai_service.generate_text(intro_prompt).strip()
        intro = normalize_paragraph(intro)

        sections: list[SectionDraft] = []
        for index, heading in enumerate(seo.h2s, start=1):
            section_prompt = (
                f"Write a single HTML paragraph of 75 to 80 words for section {index} titled '{heading}' "
                f"for the article '{seo.blog_title}'. Use this topic context: {workflow_input.topic}. "
                f"Audience: {workflow_input.audience}. Tone: {workflow_input.tone}. "
                f"Do not add a heading, bullet list, or conclusion. Return only the paragraph text."
            )
            section_content = self.openai_service.generate_text(section_prompt).strip()
            section_content = normalize_paragraph(section_content)
            sections.append(
                SectionDraft(
                    heading=heading,
                    content=section_content,
                    word_count=word_count(section_content),
                )
            )

        html_parts = [f"<h1>{seo.blog_title or workflow_input.topic}</h1>", f"<p>{intro}</p>"]
        for index, section in enumerate(sections, start=1):
            html_parts.append(f"<h2>{index}. {section.heading}</h2>")
            html_parts.append(f"<p>{section.content}</p>")
        html_content = "\n".join(html_parts)
        return BlogDraft(
            intro=intro,
            sections=sections,
            html_content=html_content,
            internal_linking_suggestions=["/services", "/blog"],
            conclusion=f"Summarize the {workflow_input.topic} ideas and encourage the reader to choose the best fit.",
        )