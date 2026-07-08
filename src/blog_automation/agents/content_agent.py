from __future__ import annotations

import re
from datetime import datetime

from blog_automation.models.workflow import (
    BlogDraft,
    ImagePlan,
    PinterestPin,
    ResearchSummary,
    SectionDraft,
    SeoOutline,
    WorkflowInput,
)
from blog_automation.services.openai_service import OpenAIService
from blog_automation.utils.html_utils import normalize_paragraph
from blog_automation.utils.text_utils import extract_section_count, word_count

PINTEREST_PIN_COUNT = 3


def _current_year_guidance() -> str:
    current_year = datetime.now().year
    return (
        f"If you mention any year, always use the current year ({current_year}) — never an "
        f"outdated year like {current_year - 2} or {current_year - 1}."
    )


def _pinterest_title_guidance() -> str:
    return (
        "If the keyword starts with or includes a number (e.g. '18'), every title must start with "
        "that exact number. Make each title compelling, specific, and scroll-stopping, not "
        "generic. Each title (including the leading number) must be between 40 and 45 characters "
        f"long — count characters carefully and stay within this range. {_current_year_guidance()}"
    )

TOP_LEVEL_RE = re.compile(
    r"<<<INTRO>>>\s*(.*?)\s*<<<HEADINGS>>>\s*(.*?)\s*<<<SECTIONS>>>\s*(.*?)\s*<<<PROMPTS>>>\s*(.*)",
    re.DOTALL,
)
SECTION_MARKER_RE = re.compile(r"<<<SECTION\s*(\d+)>>>\s*(.*?)\s*(?=<<<SECTION\s*\d+>>>|\Z)", re.DOTALL)
PROMPT_MARKER_RE = re.compile(r"<<<PROMPT\s*(\d+)>>>\s*(.*?)\s*(?=<<<PROMPT\s*\d+>>>|\Z)", re.DOTALL)
PIN_TITLE_RE = re.compile(
    r"<<<PIN_TITLE\s*(\d+)>>>\s*(.*?)\s*(?=<<<PIN_DESC\s*\d+>>>|<<<PIN_TITLE\s*\d+>>>|\Z)", re.DOTALL
)
PIN_DESC_RE = re.compile(
    r"<<<PIN_DESC\s*(\d+)>>>\s*(.*?)\s*(?=<<<PIN_TITLE\s*\d+>>>|<<<PIN_DESC\s*\d+>>>|\Z)", re.DOTALL
)


class BlogContentAgent:
    """Generates headings, intro, section content, and image prompts in a single OpenAI call.

    Falls back to small, targeted per-item calls only for whatever the model
    fails to return in the expected format, instead of regenerating everything.
    """

    def __init__(self, openai_service: OpenAIService) -> None:
        self.openai_service = openai_service

    def _truncate_to_word_count(self, text: str, target_words: int) -> str:
        cleaned = normalize_paragraph(text).strip()
        if not cleaned:
            return cleaned

        words = cleaned.split()
        if len(words) <= target_words:
            return cleaned

        truncated = " ".join(words[:target_words]).strip()
        if truncated and truncated[-1] not in ".!?":
            truncated = truncated.rstrip(",;:-") + "."
        return truncated

    def _pad_to_word_count(self, text: str, target_words: int) -> str:
        cleaned = normalize_paragraph(text).strip()
        if not cleaned:
            cleaned = ""

        words = cleaned.split()
        if len(words) >= target_words:
            return cleaned

        filler_sentences = [
            "This keeps the idea practical, clear, and easy for readers to use right away.",
            "It also adds a little more helpful detail without making the writing sound stiff.",
            "A simple, thoughtful explanation like this helps the whole article feel complete.",
            "That balance makes the advice feel more natural, more useful, and easier to follow.",
        ]
        filler_words: list[str] = []
        filler_index = 0
        while len(words) + len(filler_words) < target_words:
            remaining = target_words - (len(words) + len(filler_words))
            sentence_words = filler_sentences[filler_index % len(filler_sentences)].split()
            filler_words.extend(sentence_words[:remaining])
            filler_index += 1

        padded = " ".join(words + filler_words).strip()
        if padded and padded[-1] not in ".!?":
            padded = padded + "."
        return padded

    def _resize_to_word_count(self, text: str, target_words: int) -> str:
        cleaned = normalize_paragraph(text).strip()
        current_words = word_count(cleaned)
        if current_words > target_words:
            return self._truncate_to_word_count(cleaned, target_words)
        if current_words < target_words:
            return self._pad_to_word_count(cleaned, target_words)
        return cleaned

    def _word_budget_targets(self, section_count: int) -> tuple[int, int, list[int]]:
        total_target_words = max(3000, min(3500, section_count * 200 + 180))
        intro_target_words = min(180, total_target_words)
        remaining_words = max(0, total_target_words - intro_target_words)
        base_section_words, remainder = divmod(remaining_words, section_count)
        section_targets = [base_section_words + (1 if index < remainder else 0) for index in range(section_count)]
        return total_target_words, intro_target_words, section_targets

    def _fallback_headings(self, topic: str, section_count: int) -> list[str]:
        base_topic = re.sub(r"^\s*\d+\s*", "", topic).strip()
        if not base_topic:
            base_topic = topic.strip()
        words = base_topic.split()
        key_phrase = " ".join(words[:4]) if words else base_topic
        return [f"{key_phrase} Tip {index + 1}" for index in range(section_count)]

    def _split_into_two_paragraphs(self, text: str) -> list[str]:
        cleaned = normalize_paragraph(text).strip()
        if not cleaned:
            return [""]

        explicit_paragraphs = [part.strip() for part in re.split(r"\n\s*\n", cleaned) if part.strip()]
        if len(explicit_paragraphs) >= 2:
            return explicit_paragraphs[:2]

        words = cleaned.split()
        if len(words) < 2:
            return [cleaned]

        midpoint = len(words) // 2
        left_words = words[:midpoint]
        right_words = words[midpoint:]

        if not left_words or not right_words:
            midpoint = max(1, len(words) // 2)
            left_words = words[:midpoint]
            right_words = words[midpoint:]

        return [" ".join(left_words).strip(), " ".join(right_words).strip()]

    def _generate_intro(self, workflow_input: WorkflowInput, blog_title: str) -> str:
        prompt = (
            f"Write an introduction of 150 to 220 words for an article titled '{blog_title}'. "
            f"Audience: {workflow_input.audience}. Tone: {workflow_input.tone}. "
            f"Use simple, natural, human-sounding language that feels easy to read."
        )
        return normalize_paragraph(self.openai_service.generate_text(prompt, tag="intro_fallback").strip())

    def _generate_section_content(
        self, workflow_input: WorkflowInput, blog_title: str, heading: str, index: int
    ) -> str:
        prompt = (
            f"Write exactly two HTML paragraphs totaling 180 to 220 words for section {index} titled '{heading}' "
            f"for the article '{blog_title}'. Use this topic context: {workflow_input.topic}. "
            f"Audience: {workflow_input.audience}. Tone: {workflow_input.tone}. "
            f"Use easy words, a natural human voice, and original phrasing. Do not copy or sound generic. "
            f"Separate the two paragraphs with a blank line. Do not add a heading, bullet list, or conclusion. "
            f"Return only the paragraph text."
        )
        return normalize_paragraph(self.openai_service.generate_text(prompt, tag="section_fallback").strip())

    def _generate_image_prompt(self, workflow_input: WorkflowInput, content: str) -> str:
        prompt = (
            f"Create a concise image prompt based only on this section content: {content}. "
            f"Topic: {workflow_input.topic}. Style: professional, elegant, realistic photography. "
            f"Return only the image prompt sentence."
        )
        return self.openai_service.generate_text(prompt, tag="image_prompt_fallback").strip()

    def _generate_pinterest_pin(self, workflow_input: WorkflowInput, index: int) -> PinterestPin:
        prompt = (
            f"Write 1 Pinterest pin title (with 2 to 3 relevant hashtags included) and a short 1 to 2 "
            f"sentence Pinterest pin description for the keyword '{workflow_input.topic}'. This is option "
            f"{index} of {PINTEREST_PIN_COUNT}, so make it distinct from the other options. "
            f"{_pinterest_title_guidance()} "
            f"Return your response in exactly this format, with no extra commentary:\n"
            f"<<<TITLE>>>\n(title with hashtags)\n<<<DESC>>>\n(description)"
        )
        raw_response = self.openai_service.generate_text(prompt, tag="pinterest_fallback")
        title, _, description = raw_response.partition("<<<DESC>>>")
        title = title.replace("<<<TITLE>>>", "").strip()
        description = description.strip()
        return PinterestPin(title=title, description=description)

    def _parse_pinterest_pins(self, workflow_input: WorkflowInput, pinterest_text: str) -> list[PinterestPin]:
        pin_title_map = {int(index): content.strip() for index, content in PIN_TITLE_RE.findall(pinterest_text)}
        pin_desc_map = {int(index): content.strip() for index, content in PIN_DESC_RE.findall(pinterest_text)}

        pinterest_pins: list[PinterestPin] = []
        for index in range(1, PINTEREST_PIN_COUNT + 1):
            title = pin_title_map.get(index, "")
            description = pin_desc_map.get(index, "")
            if not title or not description:
                pin = self._generate_pinterest_pin(workflow_input, index)
            else:
                pin = PinterestPin(title=title, description=description)
            pinterest_pins.append(pin)
        return pinterest_pins

    def generate_pinterest_pins(self, workflow_input: WorkflowInput) -> list[PinterestPin]:
        """Generate only the Pinterest titles/descriptions, skipping all blog content.

        Used for the "Just Pinterest" generation mode.
        """
        prompt = (
            f"Generate exactly {PINTEREST_PIN_COUNT} different Pinterest pin titles for the keyword "
            f"'{workflow_input.topic}', each with 2 to 3 relevant hashtags included. {_pinterest_title_guidance()} "
            f"For each title, also write a short 1 to 2 sentence Pinterest pin description.\n\n"
            f"Return your response in exactly this format, with no extra commentary:\n\n"
            f"<<<PIN_TITLE 1>>>\n(pinterest title 1 with hashtags)\n"
            f"<<<PIN_DESC 1>>>\n(pinterest description 1)\n"
            f"<<<PIN_TITLE 2>>>\n(pinterest title 2 with hashtags)\n"
            f"<<<PIN_DESC 2>>>\n(pinterest description 2)\n"
            f"... continue through <<<PIN_TITLE {PINTEREST_PIN_COUNT}>>> / "
            f"<<<PIN_DESC {PINTEREST_PIN_COUNT}>>> ..."
        )
        raw_response = self.openai_service.generate_text(prompt, tag="pinterest_titles_only")
        return self._parse_pinterest_pins(workflow_input, raw_response)

    def run(
        self, workflow_input: WorkflowInput, research: ResearchSummary
    ) -> tuple[SeoOutline, BlogDraft, ImagePlan, list[PinterestPin]]:
        section_count = extract_section_count(workflow_input.topic)
        blog_title = f"{workflow_input.topic} Guide"
        total_target_words, intro_target_words, section_targets = self._word_budget_targets(section_count)
        section_target_words = section_targets[0] if section_targets else 0
        section_paragraph_target_words = max(40, section_target_words // 2)

        prompt = (
            f"Write complete content for a blog article about '{workflow_input.topic}' titled '{blog_title}'. "
            f"Audience: {workflow_input.audience}. Length target: {workflow_input.length}. Tone: {workflow_input.tone}. "
            f"Write for readers aged 18 to 44 with a modern, friendly, conversational, and engaging style. "
            f"Use easy words, sound human, and avoid stiff, robotic, or overly formal phrasing. "
            f"Make the content feel original and plagiarism-free. Number of sections: {section_count}.\n\n"
            f"Do all of the following in a single response, in this exact order:\n"
            f"1. Write an introduction of about {intro_target_words} words for the article.\n"
            f"2. Generate exactly {section_count} concise H2 headings. Each heading must be specific to the "
            f"topic, natural, and useful to the reader. Do not use placeholders like \"Idea 1\" or \"Heading 1\". "
            f"{_current_year_guidance()}\n"
            f"3. For each heading, write exactly two HTML paragraphs of about {section_paragraph_target_words} words each, for a total of "
            f"about {section_target_words} words per heading. Use simple, clear, human language and keep the writing helpful and "
            f"easy to understand. Put a blank line between the two paragraphs. Do not add a heading, bullet list, "
            f"or conclusion to any section.\n"
            f"4. For each heading, write one concise image prompt sentence based only on that section's "
            f"content, for a professional, elegant, realistic photography style image.\n"
            f"5. Generate exactly {PINTEREST_PIN_COUNT} different Pinterest pin titles for the keyword "
            f"'{workflow_input.topic}', each with 2 to 3 relevant hashtags included. {_pinterest_title_guidance()} "
            f"For each title, also write a short 1 to 2 sentence Pinterest pin description.\n\n"
            f"The full blog article must be between 3000 and 3500 words overall, including the intro and all section "
            f"paragraphs. Do not output less than 3000 words or more than 3500 words. Aim for about {total_target_words} words total.\n\n"
            f"Return your response in exactly this format, with no extra commentary:\n\n"
            f"<<<INTRO>>>\n(the introduction paragraph)\n"
            f"<<<HEADINGS>>>\n(one heading per line, exactly {section_count} headings, no numbering)\n"
            f"<<<SECTIONS>>>\n"
            f"<<<SECTION 1>>>\n(paragraph for heading 1)\n"
            f"<<<SECTION 2>>>\n(paragraph for heading 2)\n"
            f"... continue through <<<SECTION {section_count}>>> ...\n"
            f"<<<PROMPTS>>>\n"
            f"<<<PROMPT 1>>>\n(image prompt for heading 1)\n"
            f"<<<PROMPT 2>>>\n(image prompt for heading 2)\n"
            f"... continue through <<<PROMPT {section_count}>>> ...\n"
            f"<<<PINTEREST>>>\n"
            f"<<<PIN_TITLE 1>>>\n(pinterest title 1 with hashtags)\n"
            f"<<<PIN_DESC 1>>>\n(pinterest description 1)\n"
            f"<<<PIN_TITLE 2>>>\n(pinterest title 2 with hashtags)\n"
            f"<<<PIN_DESC 2>>>\n(pinterest description 2)\n"
            f"... continue through <<<PIN_TITLE {PINTEREST_PIN_COUNT}>>> / "
            f"<<<PIN_DESC {PINTEREST_PIN_COUNT}>>> ..."
        )
        raw_response = self.openai_service.generate_text(prompt, tag="content_plan")

        main_text, _, pinterest_text = raw_response.partition("<<<PINTEREST>>>")

        match = TOP_LEVEL_RE.search(main_text)
        if match:
            intro_text, headings_text, sections_text, prompts_text = match.groups()
        else:
            intro_text, headings_text, sections_text, prompts_text = "", "", "", ""

        intro = normalize_paragraph(intro_text.strip())

        section_titles = [
            line.strip("-• \t\r\n1234567890.") for line in headings_text.splitlines() if line.strip()
        ]
        section_titles = [heading for heading in section_titles if heading]
        if len(section_titles) != section_count:
            section_titles = self._fallback_headings(workflow_input.topic, section_count)

        if not intro:
            intro = self._generate_intro(workflow_input, blog_title)

        section_map = {
            int(index): normalize_paragraph(content.strip())
            for index, content in SECTION_MARKER_RE.findall(sections_text)
        }
        prompt_map = {int(index): content.strip() for index, content in PROMPT_MARKER_RE.findall(prompts_text)}

        sections: list[SectionDraft] = []
        section_prompts: list[str] = []
        alt_texts: list[str] = []
        for index, heading in enumerate(section_titles, start=1):
            content = section_map.get(index, "")
            if not content:
                content = self._generate_section_content(workflow_input, blog_title, heading, index)
            sections.append(SectionDraft(heading=heading, content=content, word_count=word_count(content)))

            image_prompt = prompt_map.get(index, "")
            if not image_prompt:
                image_prompt = self._generate_image_prompt(workflow_input, content)
            section_prompts.append(image_prompt)
            alt_texts.append(f"{heading} illustration")

        intro = self._resize_to_word_count(intro, intro_target_words)
        adjusted_section_contents = [
            self._resize_to_word_count(section.content, section_targets[index])
            for index, section in enumerate(sections)
        ]
        sections = [
            SectionDraft(
                heading=section.heading,
                content=adjusted_section_contents[index],
                word_count=word_count(adjusted_section_contents[index]),
                image_prompt=section.image_prompt,
                alt_text=section.alt_text,
            )
            for index, section in enumerate(sections)
        ]

        total_words = word_count(intro) + sum(word_count(section.content) for section in sections)
        if total_words < 3000:
            deficit = 3000 - total_words
            sections[-1] = SectionDraft(
                heading=sections[-1].heading,
                content=self._pad_to_word_count(sections[-1].content, word_count(sections[-1].content) + deficit),
                word_count=0,
                image_prompt=sections[-1].image_prompt,
                alt_text=sections[-1].alt_text,
            )
            sections[-1].word_count = word_count(sections[-1].content)
        elif total_words > 3500:
            overflow = total_words - 3500
            sections[-1] = SectionDraft(
                heading=sections[-1].heading,
                content=self._truncate_to_word_count(sections[-1].content, word_count(sections[-1].content) - overflow),
                word_count=0,
                image_prompt=sections[-1].image_prompt,
                alt_text=sections[-1].alt_text,
            )
            sections[-1].word_count = word_count(sections[-1].content)

        intro_paragraphs = self._split_into_two_paragraphs(intro)
        html_parts = [f"<h1>{blog_title or workflow_input.topic}</h1>"]
        for paragraph in intro_paragraphs:
            if paragraph:
                html_parts.append(f"<p>{paragraph}</p>")
        for index, section in enumerate(sections, start=1):
            html_parts.append(f"<h2>{index}. {section.heading}</h2>")
            paragraphs = self._split_into_two_paragraphs(section.content)
            for paragraph in paragraphs:
                if paragraph:
                    html_parts.append(f"<p>{paragraph}</p>")
        html_content = "\n".join(html_parts)

        seo = SeoOutline(
            blog_title=blog_title,
            meta_title=f"{workflow_input.topic} Guide for {workflow_input.audience}",
            meta_description=f"Learn about {workflow_input.topic} with a practical guide for {workflow_input.audience}.",
            h1=f"{workflow_input.topic}",
            h2s=section_titles,
            h3s={},
            faqs=[{"question": "What is it?", "answer": "A practical explanation."}],
            target_keywords=[workflow_input.topic.lower()],
            section_count=section_count,
            intro=intro,
        )
        blog = BlogDraft(
            intro=intro,
            sections=sections,
            html_content=html_content,
            internal_linking_suggestions=["/services", "/blog"],
            conclusion=f"Summarize the {workflow_input.topic} ideas and encourage the reader to choose the best fit.",
        )
        images = ImagePlan(cover_prompt="", section_prompts=section_prompts, alt_texts=alt_texts)

        pinterest_pins = self._parse_pinterest_pins(workflow_input, pinterest_text)

        return seo, blog, images, pinterest_pins
