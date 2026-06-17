from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import streamlit as st

from blog_automation.config import get_settings
from blog_automation.models.workflow import WorkflowInput
from blog_automation.orchestrator import BlogAutomationOrchestrator
from blog_automation.utils.text_utils import extract_section_count, slugify

# Rough per-step timings (seconds) used only to estimate progress/ETA in the UI.
# The real run time depends on OpenAI/WordPress latency, so this is an approximation.
SECONDS_INTRO_AND_OUTLINE = 10
SECONDS_PER_SECTION_TEXT = 6
SECONDS_PER_IMAGE = 22
SECONDS_PUBLISH = 5


def estimate_phase_seconds(topic: str) -> tuple[int, float, float]:
    """Return (section_count, content_phase_seconds, per_image_seconds)."""
    section_count = extract_section_count(topic)
    content_phase_seconds = SECONDS_INTRO_AND_OUTLINE + section_count * SECONDS_PER_SECTION_TEXT
    return section_count, content_phase_seconds, SECONDS_PER_IMAGE


def load_history(history_path: Path) -> list[dict]:
    if not history_path.exists():
        return []
    try:
        return json.loads(history_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_history(history_path: Path, history: list[dict]) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")


def render_history(placeholder, history_path: Path) -> None:
    history = load_history(history_path)
    with placeholder.container():
        st.markdown("---")
        st.subheader("Generated Posts")
        if not history:
            st.caption("No posts generated yet.")
        else:
            for entry in reversed(history):
                title = entry.get("title", "Untitled")
                url = entry.get("url", "")
                if url:
                    st.markdown(f"- [{title}]({url})")
                else:
                    st.markdown(f"- {title}")

# get_settings() above already loads the project .env via python-dotenv.
APP_USERNAME = os.getenv("APP_USERNAME", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")


def require_login() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Blog Automation — Login")

    if not APP_USERNAME or not APP_PASSWORD:
        st.error("APP_USERNAME / APP_PASSWORD are not set in .env. Set them before using this app.")
        return False

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Log in")

    if submitted:
        if username == APP_USERNAME and password == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")

    return False

AUDIENCE_OPTIONS = [
    "Homeowners",
    "Small Business Owners",
    "Marketers",
    "Real Estate Professionals",
    "Students",
    "General Readers",
    "Other",
]

LOCATION_OPTIONS = [
    "USA",
    "United Kingdom",
    "Canada",
    "Australia",
    "India",
    "Other",
]

st.set_page_config(page_title="Blog Automation", layout="wide")

if not require_login():
    st.stop()

settings = get_settings()
history_path = settings.output_dir / "logs" / "generated_posts.json"

with st.sidebar:
    if st.button("Log out"):
        st.session_state["authenticated"] = False
        st.rerun()
    history_placeholder = st.empty()
    render_history(history_placeholder, history_path)

st.title("Blog Automation")

with st.form("generate_form"):
    topic = st.text_input(
        "Keyword / Topic",
        placeholder="e.g. 19 Farmhouse Office Ideas for a Cozy Workspace",
    )

    col1, col2 = st.columns(2)
    with col1:
        audience_choice = st.selectbox("Audience", AUDIENCE_OPTIONS, index=0)
        if audience_choice == "Other":
            audience_choice = st.text_input("Custom audience", placeholder="e.g. Real Estate Agents")
    with col2:
        location_choice = st.selectbox("Location", LOCATION_OPTIONS, index=0)
        if location_choice == "Other":
            location_choice = st.text_input("Custom location", placeholder="e.g. Austin, TX")

    submitted = st.form_submit_button("Generate")

if submitted:
    if not topic.strip():
        st.error("Please enter a keyword / topic.")
    elif not audience_choice.strip():
        st.error("Please select or enter an audience.")
    elif not location_choice.strip():
        st.error("Please select or enter a location.")
    else:
        missing = []
        if not settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not settings.wordpress_base_url:
            missing.append("WORDPRESS_BASE_URL")
        if not settings.wordpress_username or not settings.wordpress_app_password:
            missing.append("WORDPRESS_USERNAME / WORDPRESS_APP_PASSWORD")

        if missing:
            st.error(f"Missing required settings in .env: {', '.join(missing)}")
        else:
            workflow_input = WorkflowInput(
                topic=topic.strip(),
                audience=f"{audience_choice.strip()} in {location_choice.strip()}",
                length="1500 words",
                tone="Professional",
            )

            section_count, content_phase_seconds, per_image_seconds = estimate_phase_seconds(
                workflow_input.topic
            )

            run_state: dict = {}

            def run_workflow() -> None:
                try:
                    orchestrator = BlogAutomationOrchestrator(settings)
                    run_state["result"] = orchestrator.run(workflow_input, dry_run=False)
                except Exception as exc:  # noqa: BLE001 - surfaced in the UI below
                    run_state["error"] = exc

            worker = threading.Thread(target=run_workflow, daemon=True)
            start_time = time.time()
            worker.start()

            status_text = st.empty()
            status_text.info("Generating content (intro, outline, and sections)...")

            while worker.is_alive():
                elapsed = time.time() - start_time
                if elapsed < content_phase_seconds:
                    status_text.info("Generating content (intro, outline, and sections)...")
                else:
                    image_elapsed = elapsed - content_phase_seconds
                    current_image = min(int(image_elapsed // per_image_seconds) + 1, section_count)
                    if current_image >= section_count and image_elapsed >= section_count * per_image_seconds:
                        status_text.info("Images ready. Publishing to WordPress...")
                    else:
                        status_text.info(
                            f"Content ready. Generating images... ({current_image}/{section_count})"
                        )
                time.sleep(1)

            worker.join()
            status_text.empty()

            if "error" in run_state:
                st.error(f"Generation failed: {run_state['error']}")
            else:
                result = run_state["result"]
                try:
                    topic_slug = slugify(result.seo.blog_title or workflow_input.topic)
                    draft_filename = f"{topic_slug}.html"
                    draft_path = settings.output_dir / topic_slug / draft_filename
                    html_content = draft_path.read_text(encoding="utf-8")
                except Exception as exc:
                    st.error(f"Generation succeeded but reading the draft HTML failed: {exc}")
                else:
                    history = load_history(history_path)
                    history.append(
                        {
                            "title": result.seo.blog_title or workflow_input.topic,
                            "url": result.wordpress_post_url,
                        }
                    )
                    save_history(history_path, history)
                    render_history(history_placeholder, history_path)

                    st.success("Draft generated and published to WordPress.")
                    if result.wordpress_post_url:
                        st.markdown(f"**WordPress draft:** [{result.wordpress_post_url}]({result.wordpress_post_url})")

                    st.download_button(
                        "Download HTML",
                        data=html_content,
                        file_name=draft_filename,
                        mime="text/html",
                    )

                    st.subheader("Preview")
                    st.components.v1.html(html_content, height=800, scrolling=True)

                    st.subheader("HTML Source")
                    st.code(html_content, language="html")
