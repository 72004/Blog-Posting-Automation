from __future__ import annotations

from blog_automation.models.workflow import ResearchSummary, WorkflowInput
from blog_automation.services.web_research_service import WebResearchService


class ResearchAgent:
    def __init__(self, research_service: WebResearchService) -> None:
        self.research_service = research_service

    def run(self, workflow_input: WorkflowInput) -> ResearchSummary:
        results = self.research_service.search(workflow_input.topic)
        summary_data = self.research_service.summarize_results(results)
        return ResearchSummary(
            search_results=summary_data.get("results", []),
            key_insights=summary_data.get("insights", []),
            faqs=summary_data.get("faqs", []),
            statistics=summary_data.get("statistics", []),
            summary="",
        )