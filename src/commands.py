import os
from datetime import datetime

from openai import OpenAI
from openai import APITimeoutError

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


# OpenAI API timeout in seconds
OPENAI_API_TIMEOUT = 30.0


# ToDo: make several small files, like jira_commands.....
def generate_bug_report(text: str, team_id: str, channel_id: str | None = None) -> str:
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
    settings = get_settings(team_id, channel_id=channel_id)
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
            timeout=OPENAI_API_TIMEOUT,
        )
    except APITimeoutError:
        logger.error(
            "OpenAI API timeout while generating bug report for team_id=%s (timeout=%ss)",
            team_id,
            OPENAI_API_TIMEOUT,
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
    logger.debug("Show bug report template")
    settings = get_settings(team_id, channel_id=channel_id)
    return settings["bug_report_template"]


def edit_bug_report_template(text: str, team_id: str, channel_id: str | None = None) -> str:
    logger.debug("Editing bug report template")
    _update_settings_field(team_id, channel_id, "bug_report_template", text)
    return "Bug report template updated"


def show_project_overview(team_id: str, channel_id: str | None = None) -> str:
    logger.debug("Show project overview")
    settings = get_settings(team_id, channel_id=channel_id)
    if not settings["project_context"].strip():
        return "Project documentation is empty. Use *update docs* to add it."
    return settings["project_context"]


def update_project_overview(text: str, team_id: str, channel_id: str | None = None) -> str:
    logger.debug("Updating project overview")
    _update_settings_field(team_id, channel_id, "project_context", text)
    return "Project overview updated."


def set_use_documentation(flag: bool, team_id: str, channel_id: str | None = None) -> str:
    logger.debug(f"Use documentation flag: {flag}")
    _update_settings_field(team_id, channel_id, "use_project_context", flag)
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


def set_jira_token(text: str, team_id: str, channel_id: str | None = None):
    token = strip_command(text, ["set jira token", "update jira token"]).strip()

    if len(token) < 5:
        return "Jira token looks too short. Please send a valid token."

    MAX_TOKEN_LENGTH = 4096
    if len(token) > MAX_TOKEN_LENGTH:
        return (
            f"Jira token looks unusually long. "
            f"Please ensure it's correct and shorter than {MAX_TOKEN_LENGTH} characters."
        )

    _update_settings_field(team_id, channel_id, "jira_token", token)

    return "Jira token has been updated."


def set_jira_url(text: str, team_id: str, channel_id: str | None = None):
    url = strip_command(text, ["set jira url", "update jira url"]).strip()

    if not (url.startswith("http://") or url.startswith("https://")):
        return "Jira URL should start with http:// or https://"

    MAX_URL_LENGTH = 2048
    if len(url) > MAX_URL_LENGTH:
        return (
            f"Jira URL is too long. "
            f"Please provide a URL shorter than {MAX_URL_LENGTH} characters."
        )

    _update_settings_field(team_id, channel_id, "jira_url", url)

    return "Jira URL has been updated."


def set_jira_bug_query(text: str, team_id: str, channel_id: str | None = None):
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

    _update_settings_field(team_id, channel_id, "jira_bug_query", query)

    return "Jira bug query has been updated."


def set_jira_email(text: str, team_id: str, channel_id: str | None = None):
    email = strip_command(text, ["set jira email", "update jira email"]).strip()

    if not email:
        return "Please provide a Jira email address."

    # Basic email validation
    if "@" not in email or "." not in email.split("@")[-1]:
        return "Please provide a valid email address."

    MAX_EMAIL_LENGTH = 256
    if len(email) > MAX_EMAIL_LENGTH:
        return (
            f"Jira email is too long. "
            f"Please provide an email shorter than {MAX_EMAIL_LENGTH} characters."
        )

    _update_settings_field(team_id, channel_id, "jira_email", email)

    return "Jira email has been updated."


def show_jira_bug_query(team_id: str, channel_id: str | None = None):
    # Reuse get_settings so project-specific settings are applied if channel/project is set.
    settings = get_settings(team_id, channel_id=channel_id)
    query = settings.get("jira_bug_query")

    if not query:
        return "Jira bug query is not set."

    return f"Current Jira bug query:\n```\n{query}\n```"


def get_settings(team_id: str, channel_id: str | None = None):
    """
    Get project settings. bug_report_template and project_context are stored only in projects,
    not in settings. If channel_id is provided, returns project-specific settings.
    If channel_id is None, returns empty dict (for backward compatibility).
    
    Uses atomic MongoDB operations to prevent race conditions.
    """
    PROJECT_DEFAULTS = {
        "use_project_context": False,
        "project_context": "",
        "bug_report_template": """
Bug name:
Steps:
Actual result:
Expected:
"""
    }

    # Atomically ensure org exists with required fields using upsert
    # $setOnInsert only sets these fields if document is being created
    joined_date_str = datetime.utcnow().isoformat() + "Z"
    orgs.update_one(
        {"team_id": team_id},
        {
            "$setOnInsert": {
                "team_id": team_id,
                "channel_projects": {},
                "joined_date": joined_date_str,
            }
        },
        upsert=True,
    )

    # Atomically backfill/convert joined_date if needed
    # These updates are safe because they use query conditions that match the state
    # Multiple threads can run these safely - only one will succeed per condition
    orgs.update_one(
        {"team_id": team_id, "joined_date": {"$exists": False}},
        {"$set": {"joined_date": datetime.utcnow().isoformat() + "Z"}},
    )
    
    # Convert datetime objects to ISO strings atomically
    # Note: This requires checking if it's a datetime, which we do after fetching
    # The conversion is safe because we check the type in the update condition
    
    # Atomically ensure channel_projects exists
    orgs.update_one(
        {"team_id": team_id, "channel_projects": {"$exists": False}},
        {"$set": {"channel_projects": {}}},
    )

    # Fetch org after all atomic updates to get latest state
    org = orgs.find_one({"team_id": team_id})
    
    # Handle datetime conversion if needed (one-time migration)
    # This is safe because the update condition ensures atomicity - only converts if still a datetime
    if org and isinstance(org.get("joined_date"), datetime):
        joined_date_str = org["joined_date"].isoformat() + "Z"
        orgs.update_one(
            {"team_id": team_id, "joined_date": {"$type": "date"}},
            {"$set": {"joined_date": joined_date_str}},
        )
        # Refetch to get the converted value (or value from another thread that converted it)
        org = orgs.find_one({"team_id": team_id})
    if not org:
        # Should not happen after upsert, but handle gracefully
        if channel_id is None:
            return {}
        return PROJECT_DEFAULTS

    # If no channel context → return empty dict
    if channel_id is None:
        return {}

    channel_projects = org.get("channel_projects") or {}
    channel_info = channel_projects.get(channel_id)
    
    # Handle both old format (channel_id -> project_name) and new format (channel_id -> {project: name, welcome_shown: bool})
    if isinstance(channel_info, dict):
        project_name = channel_info.get("project")
    else:
        project_name = channel_info

    # If this channel is not yet bound to a specific project, return defaults
    if not project_name:
        return PROJECT_DEFAULTS

    # Get project-specific settings
    projects = org.get("projects") or {}
    project_settings = projects.get(project_name, {})

    # Merge with defaults
    merged_project_settings = {**PROJECT_DEFAULTS, **project_settings}

    # Persist back if something changed (safe migration / initialization)
    # Use atomic update to prevent race conditions
    if merged_project_settings != project_settings:
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {f"projects.{project_name}": merged_project_settings}},
        )

    return merged_project_settings




def set_channel_project(text: str, team_id: str, channel_id: str) -> str:
    """
    Bind this Slack channel to a named project configuration within the org.
    If the project does not exist yet, it will be created with default project settings.
    Preserves welcome_shown flag in channel_projects for this channel if it exists.
    """
    project_name = strip_command(
        text,
        ["use project", "switch project", "select project"],
    ).strip()

    if not project_name:
        return (
            "Please provide a project name. Example:\n"
            "`use project Mobile app`"
        )

    if len(project_name) > 128:
        return "Project name is too long. Please use a shorter name (<= 128 characters)."

    # Store channel → project binding and preserve welcome_shown flag if it exists
    # channel_projects structure: {channel_id: {"project": project_name, "welcome_shown": bool}}
    # Preserve existing welcome_shown value if it exists, don't set it if it doesn't exist
    org = orgs.find_one({"team_id": team_id}, {"channel_projects": 1}) or {}
    channel_projects = org.get("channel_projects") or {}
    channel_info = channel_projects.get(channel_id)
    
    # Build the update object - preserve welcome_shown if it exists
    update_obj = {"project": project_name}
    if isinstance(channel_info, dict) and "welcome_shown" in channel_info:
        update_obj["welcome_shown"] = channel_info["welcome_shown"]
    
    orgs.update_one(
        {"team_id": team_id},
        {
            "$set": {
                f"channel_projects.{channel_id}": update_obj
            }
        },
        upsert=True,
    )

    # Ensure project settings exist (this will also apply defaults if needed)
    get_settings(team_id, channel_id=channel_id)

    return f"Channel is now using project configuration *{project_name}*."


def list_projects(team_id: str) -> str:
    org = orgs.find_one({"team_id": team_id}, {"projects": 1})
    projects = sorted((org or {}).get("projects", {}).keys())

    if not projects:
        return (
            "No project configurations found yet.\n"
            "You can create one by mentioning me and saying, for example:\n"
            "`use project Mobile app`"
        )

    lines = ["Available project configurations:"]
    lines.extend(f"- {name}" for name in projects)
    return "\n".join(lines)


def get_channel_project_name(team_id: str, channel_id: str) -> str | None:
    """
    Get the project name bound to a channel from channel_projects.
    Returns None if channel is not bound to a project.
    """
    org = orgs.find_one({"team_id": team_id}, {"channel_projects": 1})
    if not org:
        return None
    
    channel_projects = org.get("channel_projects") or {}
    channel_info = channel_projects.get(channel_id)
    
    if isinstance(channel_info, dict):
        return channel_info.get("project")
    elif channel_info:
        # Handle old format where channel_id directly maps to project name
        return channel_info
    return None


def get_channel_welcome_shown(team_id: str, channel_id: str) -> bool:
    """
    Get whether the welcome message has been shown for a channel from channel_projects.
    Returns False if not set or channel not found.
    """
    org = orgs.find_one({"team_id": team_id}, {"channel_projects": 1})
    if not org:
        return False
    
    channel_projects = org.get("channel_projects") or {}
    channel_info = channel_projects.get(channel_id)
    
    if isinstance(channel_info, dict):
        return channel_info.get("welcome_shown", False)
    return False


def set_channel_welcome_shown(team_id: str, channel_id: str, value: bool) -> None:
    """
    Set whether the welcome message has been shown for a channel in channel_projects.
    """
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {f"channel_projects.{channel_id}.welcome_shown": value}},
        upsert=True,
    )


def show_channel_status(team_id: str, channel_id: str | None) -> str:
    """
    Show the current channel status including project name, project context, use_project_context flag,
    Jira URL, and Jira token status.
    """
    if not channel_id:
        return "Channel status is only available when called from a channel."
    
    project_name = get_channel_project_name(team_id, channel_id)
    settings = get_settings(team_id, channel_id=channel_id)
    
    project_context = settings.get("project_context", "").strip()
    use_project_context = settings.get("use_project_context", False)
    jira_url = settings.get("jira_url", "").strip()
    jira_token = settings.get("jira_token", "").strip()
    jira_email = settings.get("jira_email", "").strip()
    
    lines = []
    lines.append(f"*Project name:* {project_name if project_name else 'N/A'}")
    lines.append(f"*Project context:* {project_context if project_context else 'N/A'}")
    lines.append(f"*Use project context:* {use_project_context}")
    lines.append(f"*Jira URL:* {jira_url if jira_url else 'N/A'}")
    lines.append(f"*Jira token:* {'set' if jira_token else 'not set'}")
    lines.append(f"*Jira email:* {jira_email if jira_email else 'N/A'}")
    
    return "\n".join(lines)


def _update_settings_field(team_id: str, channel_id: str | None, field: str, value) -> None:
    """
    Update a configuration field. Project-specific fields (bug_report_template, project_context,
    use_project_context, jira_*) are stored in projects.
    
    If channel_id is provided and channel is bound to a project, update that project.
    If channel_id is None or channel is not bound to a project, create/use a default project
    for project-specific fields.
    """
    # Fields that belong in projects
    PROJECT_FIELDS = {
        "bug_report_template",
        "project_context",
        "use_project_context",
        "jira_token",
        "jira_url",
        "jira_bug_query",
        "jira_email",
    }
    
    org = orgs.find_one({"team_id": team_id}) or {}
    
    # For project-specific fields, always update projects
    if field in PROJECT_FIELDS:
        if channel_id is not None:
            channel_projects = org.get("channel_projects") or {}
            channel_info = channel_projects.get(channel_id)
            
            # Handle both old format (channel_id -> project_name) and new format (channel_id -> {project: name})
            if isinstance(channel_info, dict):
                project_name = channel_info.get("project")
            else:
                project_name = channel_info
            
            if project_name:
                # Update the bound project
                orgs.update_one(
                    {"team_id": team_id},
                    {"$set": {f"projects.{project_name}.{field}": value}},
                    upsert=True,
                )
                return
        
        # If no channel_id or channel not bound to project, use/create default project
        # Default project name is "default"
        default_project = "default"
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {f"projects.{default_project}.{field}": value}},
            upsert=True,
        )
        return
    
    # Unknown field - default to project update
    if channel_id is not None:
        channel_projects = org.get("channel_projects") or {}
        channel_info = channel_projects.get(channel_id)
        
        # Handle both old format (channel_id -> project_name) and new format (channel_id -> {project: name})
        if isinstance(channel_info, dict):
            project_name = channel_info.get("project")
        else:
            project_name = channel_info
            
        if project_name:
            orgs.update_one(
                {"team_id": team_id},
                {"$set": {f"projects.{project_name}.{field}": value}},
                upsert=True,
            )
            return
    
    # Fallback: update in default project
    default_project = "default"
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {f"projects.{default_project}.{field}": value}},
        upsert=True,
    )
