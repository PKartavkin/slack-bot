"""
Bug report generation and template management commands.
"""
import os

from openai import OpenAI
from openai import APITimeoutError

from bot.logger import logger
from bot.utils import strip_command, get_mongodb_error_message
from bot.rate_limiter import openai_rate_limiter
from bot.constants import (
    OPENAI_API_TIMEOUT_SECONDS,
    OPENAI_TEMPERATURE,
    OPENAI_MODEL,
    MAX_BUG_REPORT_INPUT_LENGTH,
)
from bot.project_commands import (
    _require_project,
    get_settings,
    _update_settings_field,
)

# Initialize OpenAI client - assumes OPENAI_API_KEY is validated at startup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None


def generate_bug_report(text: str, team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    if client is None:
        return (
            "Bug report generation is temporarily unavailable: "
            "OpenAI API key is not configured."
        )

    # Rate limit OpenAI API calls - 100 requests per organization per day
    is_allowed, error_msg = openai_rate_limiter.is_allowed(team_id)
    if not is_allowed:
        return error_msg

    if len(text) > MAX_BUG_REPORT_INPUT_LENGTH:
        logger.warning(
            "Bug report input too long (len=%s) for team_id=%s", len(text), team_id
        )
        return (
            f"Your message is too long for bug report generation. "
            f"Please shorten it to under {MAX_BUG_REPORT_INPUT_LENGTH} characters."
        )

    logger.debug("Creating formatting")
    try:
        settings = get_settings(team_id, channel_id=channel_id)
    except Exception as e:
        return get_mongodb_error_message(e, "generate_bug_report")
    context_block = (
        settings["project_context"]
        if settings["use_project_context"] and settings["project_context"].strip()
        else ""
    )
    prompt = f"""
    Convert the user's message into a bug report.

    {context_block}

    Use the following format exactly:
    {settings['bug_report_template']}

    Rules:
    - If project context is disabled or empty, ignore it.
    - Bug name must be short (3–6 words).
    - Steps must be numbered and reproducible.
    - Infer details only when logically obvious.
    - If the user input is too short to create a meaningful bug report, respond with: "Too short for bug report".
    - Output only the bug report in the template format.

    User input: {text}
    """

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=OPENAI_TEMPERATURE,
            timeout=OPENAI_API_TIMEOUT_SECONDS,
        )
    except APITimeoutError:
        logger.error(
            "OpenAI API timeout while generating bug report for team_id=%s (timeout=%ss)",
            team_id,
            OPENAI_API_TIMEOUT_SECONDS,
        )
        return (
            "The AI service took too long to respond. "
            "Please try again with a shorter message or try again later."
        )
    except Exception as e:  # noqa: BLE001 - want to catch all OpenAI client errors
        logger.exception("OpenAI error while generating bug report for team_id=%s", team_id)
        return (
            "I couldn't generate a bug report due to an internal error talking to the AI service. "
            "Please try again in a bit."
        )

    content = (response.choices[0].message.content or "").strip()
    if not content:
        logger.error("OpenAI returned empty content for bug report, team_id=%s", team_id)
        return (
            "I couldn't generate a bug report from this message. "
            "Please try rephrasing or adding more details."
        )

    return content


def show_bug_report_template(team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    logger.debug("Show bug report template")
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        return settings["bug_report_template"]
    except Exception as e:
        return get_mongodb_error_message(e, "show_bug_report_template")


def edit_bug_report_template(text: str, team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    logger.debug("Editing bug report template")
    payload = strip_command(text, "edit bug template").strip()
    
    if not payload:
        return "Please provide the bug report template content."
    
    try:
        _update_settings_field(team_id, channel_id, "bug_report_template", payload)
        return "Bug report template updated"
    except Exception as e:
        return get_mongodb_error_message(e, "edit_bug_report_template")


def show_project_overview(team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    logger.debug("Show project overview")
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        if not settings["project_context"].strip():
            return "Project documentation is empty. Use *update docs* to add it."
        return settings["project_context"]
    except Exception as e:
        return get_mongodb_error_message(e, "show_project_overview")


def update_project_overview(text: str, team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    logger.debug("Updating project overview")
    payload = strip_command(text, "update docs").strip()
    
    if not payload:
        return "Please provide project documentation content."
    
    try:
        _update_settings_field(team_id, channel_id, "project_context", payload)
        return "Project overview updated."
    except Exception as e:
        return get_mongodb_error_message(e, "update_project_overview")


def set_use_documentation(flag: bool, team_id: str, channel_id: str | None = None) -> str:
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    logger.debug(f"Use documentation flag: {flag}")
    try:
        _update_settings_field(team_id, channel_id, "use_project_context", flag)
        return f"Use documentation: {flag}"
    except Exception as e:
        return get_mongodb_error_message(e, "set_use_documentation")
