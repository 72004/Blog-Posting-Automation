from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowInput:
    topic: str
    audience: str
    length: str
    tone: str


@dataclass
class ResearchSummary:
    search_results: list[dict[str, Any]] = field(default_factory=list)
    key_insights: list[str] = field(default_factory=list)
    faqs: list[str] = field(default_factory=list)
    statistics: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class SectionDraft:
    heading: str
    content: str
    word_count: int
    image_prompt: str = ""
    alt_text: str = ""


@dataclass
class SeoOutline:
    blog_title: str = ""
    meta_title: str = ""
    meta_description: str = ""
    h1: str = ""
    h2s: list[str] = field(default_factory=list)
    h3s: dict[str, list[str]] = field(default_factory=dict)
    faqs: list[dict[str, str]] = field(default_factory=list)
    target_keywords: list[str] = field(default_factory=list)
    section_count: int = 3
    intro: str = ""


@dataclass
class BlogDraft:
    intro: str = ""
    sections: list[SectionDraft] = field(default_factory=list)
    html_content: str = ""
    internal_linking_suggestions: list[str] = field(default_factory=list)
    conclusion: str = ""


@dataclass
class ImagePlan:
    cover_prompt: str = ""
    section_prompts: list[str] = field(default_factory=list)
    alt_texts: list[str] = field(default_factory=list)


@dataclass
class WordPressMediaItem:
    image_path: str
    media_id: int | None = None
    url: str = ""


@dataclass
class PinterestPin:
    title: str = ""
    description: str = ""
    image_path: str = ""


@dataclass
class WorkflowResult:
    input: WorkflowInput
    research: ResearchSummary
    seo: SeoOutline
    blog: BlogDraft
    images: ImagePlan
    media: list[WordPressMediaItem] = field(default_factory=list)
    pinterest_pins: list[PinterestPin] = field(default_factory=list)
    wordpress_post_id: int | None = None
    wordpress_post_url: str = ""