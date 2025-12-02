import os

from openai import OpenAI

from src.db import orgs
from src.logger import logger
from src.utils import strip_command


# Initialize OpenAI client lazily / defensively so missing env vars
# do not break module import (which would cause ImportError in app.py).
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    client = OpenAI(api_key=OPENAI_API_KEY)
else:
    client = None
    logger.warning(
        "OPENAI_API_KEY is not set; bug report generation will be disabled."
    )


# ToDo: make several small files, like jira_commands.....
def generate_bug_report(text: str, team_id: str) -> str:
    if client is None:
        logger.error("OPENAI_API_KEY not configured; cannot generate bug report.")
        return (
            "Bug report generation is temporarily unavailable: "
            "missing OpenAI configuration."
        )

    MAX_INPUT_LENGTH = 4000
    if len(text) > MAX_INPUT_LENGTH:
        logger.warning(
            "Bug report input too long (len=%s) for team_id=%s", len(text), team_id
        )
        return (
            f"Your message is too long for bug report generation. "
            f"Please shorten it to under {MAX_INPUT_LENGTH} characters."
        )

    logger.debug("Creating formatting")
    settings = get_settings(team_id)
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
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
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


def show_bug_report_template(team_id) -> str:
    logger.debug("Show bug report template")
    settings = get_settings(team_id)
    return settings["bug_report_template"]


def edit_bug_report_template(text: str, team_id: str) -> str:
    logger.debug("Editing bug report template")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.bug_report_template": text}},
        upsert=True
    )
    return "Bug report template updated"


def show_project_overview(team_id: str) -> str:
    logger.debug("Show project overview")
    settings = get_settings(team_id)
    if not settings["project_context"].strip():
        return "Project documentation is empty. Use *update docs* to add it."
    return settings["project_context"]


def update_project_overview(text: str, team_id: str) -> str:
    logger.debug("Updating project overview")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.project_context": text}},
        upsert=True
    )
    return "Project overview updated."


def set_use_documentation(flag: bool, team_id) -> str:
    logger.debug(f"Use documentation flag: {flag}")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.use_project_context": flag}},
        upsert=True
    )
    return f"Use documentation: {flag}"


def get_help() -> str:
    logger.debug("Help")
    return """
    **Available commands:**
    **create bug report** - formats your input according to the template using knowledge about your project
    **show bug report** - shows template for bug reports
    **edit bug report**
    **about project** - displays information about your project
    **update docs**
    **use docs** - bot will used project documentation for bug reports
    **ignore docs** - bot will ignore docs
    """


def set_jira_token(text: str, team_id: str):
    token = strip_command(text, ["set jira token", "update jira token"]).strip()

    if len(token) < 5:
        return "Jira token looks too short. Please send a valid token."

    MAX_TOKEN_LENGTH = 4096
    if len(token) > MAX_TOKEN_LENGTH:
        return (
            f"Jira token looks unusually long. "
            f"Please ensure it's correct and shorter than {MAX_TOKEN_LENGTH} characters."
        )

    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.jira_token": token}},
        upsert=True
    )

    return "Jira token has been updated."


def set_jira_url(text: str, team_id: str):
    url = strip_command(text, ["set jira url", "update jira url"]).strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        return "Jira URL should start with http:// or https://"

    MAX_URL_LENGTH = 2048
    if len(url) > MAX_URL_LENGTH:
        return (
            f"Jira URL is too long. "
            f"Please provide a URL shorter than {MAX_URL_LENGTH} characters."
        )

    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.jira_url": url}},
        upsert=True
    )

    return "Jira URL has been updated."


def set_jira_bug_query(text: str, team_id: str):
    query = strip_command(
        text,
        ["set jira query", "jira bug query", "update jira query"]
    ).strip()

    if len(query) < 5:
        return "Jira query looks too short. Please provide a valid JQL query."

    MAX_QUERY_LENGTH = 8000
    if len(query) > MAX_QUERY_LENGTH:
        return (
            f"Jira query is too long. "
            f"Please shorten it to under {MAX_QUERY_LENGTH} characters."
        )

    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.jira_bug_query": query}},
        upsert=True
    )

    return "Jira bug query has been updated."


def show_jira_bug_query(team_id: str):
    org = orgs.find_one({"team_id": team_id}, {"settings": 1})

    if not org or "settings" not in org:
        return "No Jira settings found yet."

    query = org["settings"].get("jira_bug_query")

    if not query:
        return "Jira bug query is not set."

    return f"Current Jira bug query:\n```\n{query}\n```"


def get_settings(team_id: str):
    DEFAULTS = {
        "use_project_context": False,
        "project_context": "",
        # channel_id -> bool (whether welcome message was shown in that channel)
        "channel_welcomes": {},
        "bug_report_template": """
Bug name:
Steps:
Actual result:
Expected:
"""
    }

    org = orgs.find_one({"team_id": team_id})

    # If first interaction → create entry in DB
    if not org:
        orgs.insert_one({
            "team_id": team_id,
            "settings": DEFAULTS
        })
        return DEFAULTS

    settings = org.get("settings", {})

    # If settings exist but incomplete → fill missing fields (safe migration)
    merged = {**DEFAULTS, **settings}

    # If something was missing — update DB once
    if merged != settings:
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {"settings": merged}}
        )

    return merged


def mark_channel_welcome_shown(team_id: str, channel_id: str) -> None:
    """
    Mark that the welcome message has been shown in this channel for this team.
    """
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {f"settings.channel_welcomes.{channel_id}": True}},
        upsert=True,
    )
