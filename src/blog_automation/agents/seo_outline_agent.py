from __future__ import annotations

import re

from blog_automation.models.workflow import ResearchSummary, SeoOutline, WorkflowInput
from blog_automation.services.openai_service import OpenAIService
from blog_automation.utils.text_utils import extract_section_count


class SeoOutlineAgent:
    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def _fallback_headings(self, topic: str, section_count: int) -> list[str]:
        base_topic = re.sub(r"^\s*\d+\s*", "", topic).strip()
        if not base_topic:
            base_topic = topic.strip()

        words = base_topic.split()
        key_phrase = " ".join(words[:4]) if words else base_topic
        return [f"{key_phrase} Tip {index + 1}" for index in range(section_count)]

    def run(self, workflow_input: WorkflowInput, research: ResearchSummary) -> SeoOutline:
        section_count = extract_section_count(workflow_input.topic)
        prompt = (
            f"Generate exactly {section_count} concise H2 headings for a blog post about '{workflow_input.topic}'. "
            f"Each heading must be specific to the topic, natural, and useful to the reader. "
            f"Do not use placeholders like Idea 1 or Heading 1. "
            f"Audience: {workflow_input.audience}. Length: {workflow_input.length}. Tone: {workflow_input.tone}. "
            f"Return one heading per line only."
        )
        raw_headings = self.openai_service.generate_text(prompt)
        section_titles = [
            line.strip("-• \t\r\n1234567890.")
            for line in raw_headings.splitlines()
            if line.strip()
        ]
        section_titles = [heading for heading in section_titles if heading]
        if len(section_titles) != section_count:
            section_titles = self._fallback_headings(workflow_input.topic, section_count)

        return SeoOutline(
            blog_title=f"{workflow_input.topic} Guide",
            meta_title=f"{workflow_input.topic} Guide for {workflow_input.audience}",
            meta_description=f"Learn about {workflow_input.topic} with a practical guide for {workflow_input.audience}.",
            h1=f"{workflow_input.topic}",
            h2s=section_titles,
            h3s={},
            faqs=[{"question": "What is it?", "answer": "A practical explanation."}],
            target_keywords=[workflow_input.topic.lower()],
            section_count=section_count,
        )