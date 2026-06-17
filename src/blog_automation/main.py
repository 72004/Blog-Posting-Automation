from __future__ import annotations

import argparse

from blog_automation.config import get_settings
from blog_automation.models.workflow import WorkflowInput
from blog_automation.orchestrator import BlogAutomationOrchestrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blog automation workflow")
    parser.add_argument("--topic", required=True)
    parser.add_argument("--audience", required=True)
    parser.add_argument("--length", default="1500 words")
    parser.add_argument("--tone", default="Professional")
    parser.add_argument("--dry-run", action="store_true", help="Generate content and images locally without posting to WordPress")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = get_settings()

    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required")
    if not args.dry_run:
        if not settings.wordpress_base_url:
            raise RuntimeError("WORDPRESS_BASE_URL is required")
        if not settings.wordpress_username or not settings.wordpress_app_password:
            raise RuntimeError("WORDPRESS_USERNAME and WORDPRESS_APP_PASSWORD are required")

    orchestrator = BlogAutomationOrchestrator(settings)
    result = orchestrator.run(
        WorkflowInput(
            topic=args.topic,
            audience=args.audience,
            length=args.length,
            tone=args.tone,
        ),
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(f"Dry run complete. HTML draft saved under: {settings.output_dir}")
        print(f"WordPress upload skipped. Post ID: {result.wordpress_post_id}, URL: {result.wordpress_post_url}")
    else:
        print(f"Draft created: {result.wordpress_post_url}")


if __name__ == "__main__":
    main()