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
from blog_automation.services.wordpress_service import WordPressConfig
from blog_automation.utils.text_utils import extract_section_count, slugify

# Rough per-step timings (seconds) used only to estimate progress/ETA in the UI.
# The real run time depends on OpenAI/WordPress latency, so this is an approximation.
SECONDS_INTRO_AND_OUTLINE = 10
SECONDS_PER_SECTION_TEXT = 6
SECONDS_PER_IMAGE = 22
SECONDS_PUBLISH = 5
SECONDS_PINTEREST_TITLES = 8
PINTEREST_PIN_COUNT = 3


def estimate_phase_boundaries(topic: str) -> dict:
    """Return elapsed-seconds boundaries (from run start) for each generation phase."""
    section_count = extract_section_count(topic)
    content_end = SECONDS_INTRO_AND_OUTLINE + section_count * SECONDS_PER_SECTION_TEXT
    image_end = content_end + section_count * SECONDS_PER_IMAGE
    publish_end = image_end + SECONDS_PUBLISH
    pinterest_titles_end = publish_end + SECONDS_PINTEREST_TITLES
    pinterest_images_end = pinterest_titles_end + PINTEREST_PIN_COUNT * SECONDS_PER_IMAGE
    return {
        "section_count": section_count,
        "content_end": content_end,
        "image_end": image_end,
        "publish_end": publish_end,
        "pinterest_titles_end": pinterest_titles_end,
        "pinterest_images_end": pinterest_images_end,
    }


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


def render_pinterest_pins(pins: list) -> None:
    if not pins:
        return
    st.subheader("Pinterest Pins")
    for pin_index, pin in enumerate(pins, start=1):
        pin_col_image, pin_col_text = st.columns([1, 2])
        with pin_col_image:
            if pin.image_path:
                st.image(pin.image_path)
        with pin_col_text:
            st.markdown(f"**Title:** {pin.title}")
            st.markdown(f"**Description:** {pin.description}")
            if pin.image_path:
                pin_image_bytes = Path(pin.image_path).read_bytes()
                st.download_button(
                    f"Download Pin {pin_index}",
                    data=pin_image_bytes,
                    file_name=Path(pin.image_path).name,
                    mime="image/png",
                    key=f"pinterest_download_{pin_index}",
                )

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

WEBSITE_OPTIONS = {
    "JobFO (jobf0.com)": "jobfo",
    "The Blog Home (thebloghome.com)": "blog_home",
}


def get_wordpress_credentials(settings, website_key: str) -> tuple[str, str, str]:
    if website_key == "blog_home":
        return settings.blog_home_base_url, settings.blog_home_username, settings.blog_home_password
    return settings.wordpress_base_url, settings.wordpress_username, settings.wordpress_app_password


with st.sidebar:
    st.subheader("Website")
    website_label = st.selectbox("Post destination", list(WEBSITE_OPTIONS.keys()))
    selected_website = WEBSITE_OPTIONS[website_label]
    st.markdown("---")
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
        wp_base_url, wp_username, wp_app_password = get_wordpress_credentials(settings, selected_website)

        missing = []
        if not settings.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not wp_base_url:
            missing.append(f"{website_label} base URL")
        if not wp_username or not wp_app_password:
            missing.append(f"{website_label} username/password")

        if missing:
            st.error(f"Missing required settings in .env: {', '.join(missing)}")
        else:
            workflow_input = WorkflowInput(
                topic=topic.strip(),
                audience=f"{audience_choice.strip()} in {location_choice.strip()}",
                length="1500 words",
                tone="Professional",
            )

            wordpress_config = WordPressConfig(
                base_url=wp_base_url, username=wp_username, app_password=wp_app_password
            )

            phases = estimate_phase_boundaries(workflow_input.topic)
            section_count = phases["section_count"]

            run_state: dict = {}

            def run_workflow() -> None:
                try:
                    orchestrator = BlogAutomationOrchestrator(settings, wordpress_config=wordpress_config)
                    run_state["result"] = orchestrator.run(workflow_input, dry_run=False)
                    run_state["usage"] = orchestrator.openai_service.summary
                except Exception as exc:  # noqa: BLE001 - surfaced in the UI below
                    run_state["error"] = exc

            worker = threading.Thread(target=run_workflow, daemon=True)
            start_time = time.time()
            worker.start()

            status_text = st.empty()
            status_text.info("Sending text request: generating content (intro, outline, and sections)...")

            while worker.is_alive():
                elapsed = time.time() - start_time
                if elapsed < phases["content_end"]:
                    status_text.info(
                        "Sending text request: generating content (intro, outline, and sections)..."
                    )
                elif elapsed < phases["image_end"]:
                    image_elapsed = elapsed - phases["content_end"]
                    current_image = min(int(image_elapsed // SECONDS_PER_IMAGE) + 1, section_count)
                    status_text.info(
                        f"Sending image request: generating section image... ({current_image}/{section_count})"
                    )
                elif elapsed < phases["publish_end"]:
                    status_text.info("Images ready. Publishing to WordPress...")
                elif elapsed < phases["pinterest_titles_end"]:
                    status_text.info("Sending text request: generating Pinterest titles...")
                elif elapsed < phases["pinterest_images_end"]:
                    pin_elapsed = elapsed - phases["pinterest_titles_end"]
                    current_pin = min(int(pin_elapsed // SECONDS_PER_IMAGE) + 1, PINTEREST_PIN_COUNT)
                    status_text.info(
                        f"Sending image request: generating Pinterest image... ({current_pin}/{PINTEREST_PIN_COUNT})"
                    )
                else:
                    status_text.info("Finishing up...")
                time.sleep(1)

            worker.join()
            status_text.empty()

            if "error" in run_state:
                st.session_state.pop("has_result", None)
                st.error(f"Generation failed: {run_state['error']}")
            else:
                result = run_state["result"]
                try:
                    topic_slug = slugify(result.seo.blog_title or workflow_input.topic)
                    draft_filename = f"{topic_slug}.html"
                    draft_path = settings.output_dir / topic_slug / draft_filename
                    html_content = draft_path.read_text(encoding="utf-8")
                except Exception as exc:
                    st.session_state.pop("has_result", None)
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

                    st.session_state["has_result"] = True
                    st.session_state["last_result"] = result
                    st.session_state["last_html_content"] = html_content
                    st.session_state["last_draft_filename"] = draft_filename
                    st.session_state["last_usage"] = run_state.get("usage")

# Renders the most recent result on every script run (not just right after clicking
# Generate) so it survives reruns triggered by Download button clicks.
if st.session_state.get("has_result"):
    result = st.session_state["last_result"]
    html_content = st.session_state["last_html_content"]
    draft_filename = st.session_state["last_draft_filename"]
    usage = st.session_state.get("last_usage")

    st.success("Draft generated and published to WordPress.")
    if result.wordpress_post_url:
        st.markdown(f"**WordPress draft:** [{result.wordpress_post_url}]({result.wordpress_post_url})")

    if usage:
        st.caption(
            f"OpenAI usage this run: {usage['total_requests']} requests "
            f"({usage['text_requests']} text, {usage['image_requests']} image) — "
            f"{usage['total_input_tokens']} input / {usage['total_output_tokens']} output tokens."
        )

    st.download_button(
        "Download HTML",
        data=html_content,
        file_name=draft_filename,
        mime="text/html",
        key="download_html_button",
    )

    st.subheader("Preview")
    st.components.v1.html(html_content, height=800, scrolling=True)

    st.subheader("HTML Source")
    st.code(html_content, language="html")

    render_pinterest_pins(result.pinterest_pins)
