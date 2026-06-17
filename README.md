# Blog Automation Workflow

Python workflow for generating researched, SEO-optimized blog drafts with OpenAI and publishing them to WordPress as drafts.

## Structure

- `src/blog_automation/main.py` - CLI entry point
- `src/blog_automation/orchestrator.py` - Coordinates the end-to-end workflow
- `src/blog_automation/agents/` - Research, SEO, writing, and image prompt agents
- `src/blog_automation/services/` - OpenAI, WordPress, image, and research integrations
- `src/blog_automation/models/` - Typed data models for workflow payloads
- `src/blog_automation/output/` - Local drafts, images, and logs

## Setup

1. Copy `.env.example` to `.env` and fill in your credentials.
2. Install dependencies from `requirements.txt` in your conda environment.
3. Run the CLI:

```bash
python -m blog_automation.main --topic "Your topic" --audience "Your audience" --length "1500 words" --tone "Professional"
```

## Workflow

1. Research the topic and collect insights, FAQs, and statistics.
2. Generate SEO metadata and outline.
3. Write the full HTML blog post.
4. Create image prompts and alt text.
5. Generate images locally.
6. Upload media to WordPress.
7. Assemble the HTML content.
8. Create a WordPress draft post.
9. Review and publish manually.