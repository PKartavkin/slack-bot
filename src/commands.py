import os
import unicodedata
from datetime import datetime

from jira import JIRA
from jira.exceptions import JIRAError

from openai import OpenAI
from openai import APITimeoutError

from src.db import orgs
from src.logger import logger
from src.utils import (
    strip_command,
    sanitize_slack_id,
    sanitize_project_name,
    get_mongodb_error_message,
)
from src.rate_limiter import openai_rate_limiter

# Initialize OpenAI client - assumes OPENAI_API_KEY is validated at startup
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

# OpenAI API timeout in seconds
OPENAI_API_TIMEOUT = 30.0


# ToDo: make several small files, like jira_commands.....
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


def get_help() -> str:
    logger.debug("Help")
    return """
    **Available commands:**
    
    *General:*
    **help** - show this help message
    **status** - show current channel status and project configuration
    
    *Project Management:*
    **list projects** - list all available project configurations
    **use project <name>** - bind channel to a project configuration
    
    *Bug Reports:*
    **create bug report** - format your message into a structured bug report
    **show bug template** - show the current bug report template
    **edit bug template** - edit the bug report template
    
    *Documentation:*
    **show project** - display project documentation/overview
    **update docs** - update project documentation
    **enable docs** - enable using project docs for bug reports
    **disable docs** - disable using project docs for bug reports
    
    *Jira Configuration:*
    **set jira token <token>** - set Jira API token
    **set jira url <url>** - set Jira instance URL
    **set jira email <email>** - set Jira email address
    **set jira query <JQL>** - set JQL query for fetching bugs
    **show jira query** - show current Jira JQL query
    
    *Jira Default Fields:*
    **set jira defaults field=value** - set Jira default field values (supports multiple: field1=value1 field2=value2)
    **show jira defaults** - show all Jira default field values
    **clear jira default <field>** - clear a Jira default field value
    
    *Jira Operations:*
    **test jira** - test Jira connection for current project
    **get bugs** - get list of Jira issues using the configured JQL query
    """


def set_jira_token(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    token = strip_command(text, "set jira token").strip()

    if not token:
        return "Please provide a Jira token. Example: `set jira token <your-token>`"

    if len(token) < 5:
        return "Jira token looks too short. Please send a valid token."

    MAX_TOKEN_LENGTH = 4096
    if len(token) > MAX_TOKEN_LENGTH:
        return (
            f"Jira token looks unusually long. "
            f"Please ensure it's correct and shorter than {MAX_TOKEN_LENGTH} characters."
        )

    try:
        logger.info(
            "Updating Jira token for team_id=%s, channel_id=%s (token length: %s)",
            team_id, channel_id, len(token)
        )
        _update_settings_field(team_id, channel_id, "jira_token", token)
        logger.info("Jira token updated successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        return "Jira token has been updated."
    except Exception as e:
        logger.error("Error updating Jira token for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception updating Jira token")
        return get_mongodb_error_message(e, "set_jira_token")


def set_jira_url(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    url = strip_command(text, "set jira url")
    
    # Remove Slack link formatting if present (e.g., <https://...|text>)
    if url.startswith('<') and url.endswith('>'):
        # Extract URL from Slack link format
        if '|' in url:
            url = url[1:url.index('|')]
        else:
            url = url[1:-1]
    
    # Clean the URL: normalize Unicode and strip whitespace
    url = unicodedata.normalize('NFKC', url)
    # Remove zero-width and other problematic invisible characters
    url = url.replace('\u200b', '').replace('\u200c', '').replace('\u200d', '').replace('\ufeff', '')
    # Strip all types of whitespace (including non-breaking spaces)
    url = url.strip().replace('\u00a0', ' ').strip()

    if not url:
        return "Please provide a Jira URL. Example: `set jira url https://your-instance.atlassian.net`"

    # Check if URL starts with http:// or https:// (case-insensitive)
    url_lower = url.lower()
    starts_with_http = url_lower.startswith("http://")
    starts_with_https = url_lower.startswith("https://")
    
    if not (starts_with_http or starts_with_https):
        logger.error(
            f"URL validation failed. Input: {repr(text)}, Extracted: {repr(url)}, "
            f"Length: {len(url)}, First char code: {ord(url[0]) if url else 'N/A'}, "
            f"First 10 chars: {repr(url[:10])}"
        )
        return f"Jira URL should start with http:// or https://. Got: {repr(url[:60])}"

    MAX_URL_LENGTH = 2048
    if len(url) > MAX_URL_LENGTH:
        return (
            f"Jira URL is too long. "
            f"Please provide a URL shorter than {MAX_URL_LENGTH} characters."
        )

    try:
        logger.info("Updating Jira URL for team_id=%s, channel_id=%s, URL=%s", team_id, channel_id, url)
        _update_settings_field(team_id, channel_id, "jira_url", url)
        logger.info("Jira URL updated successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        return "Jira URL has been updated."
    except Exception as e:
        logger.error("Error updating Jira URL for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception updating Jira URL")
        return get_mongodb_error_message(e, "set_jira_url")


def set_jira_bug_query(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    query = strip_command(text, "set jira query").strip()

    if not query:
        return "Please provide a JQL query. Example: `set jira query project = PROJ AND status != Done`"

    if len(query) < 5:
        return "Jira query looks too short. Please provide a valid JQL query."

    MAX_QUERY_LENGTH = 8000
    if len(query) > MAX_QUERY_LENGTH:
        return (
            f"Jira query is too long. "
            f"Please shorten it to under {MAX_QUERY_LENGTH} characters."
        )

    try:
        logger.info(
            "Updating Jira bug query for team_id=%s, channel_id=%s, query_length=%s",
            team_id, channel_id, len(query)
        )
        logger.debug("Jira bug query for team_id=%s, channel_id=%s: %s", team_id, channel_id, query)
        _update_settings_field(team_id, channel_id, "jira_bug_query", query)
        logger.info("Jira bug query updated successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        return "Jira bug query has been updated."
    except Exception as e:
        logger.error("Error updating Jira bug query for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception updating Jira bug query")
        return get_mongodb_error_message(e, "set_jira_bug_query")


def set_jira_email(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    email = strip_command(text, "set jira email").strip()

    if not email:
        return "Please provide a Jira email address. Example: `set jira email user@example.com`"

    # Basic email validation
    if "@" not in email or "." not in email.split("@")[-1]:
        return "Please provide a valid email address."

    MAX_EMAIL_LENGTH = 256
    if len(email) > MAX_EMAIL_LENGTH:
        return (
            f"Jira email is too long. "
            f"Please provide an email shorter than {MAX_EMAIL_LENGTH} characters."
        )

    try:
        logger.info("Updating Jira email for team_id=%s, channel_id=%s, email=%s", team_id, channel_id, email)
        _update_settings_field(team_id, channel_id, "jira_email", email)
        logger.info("Jira email updated successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        return "Jira email has been updated."
    except Exception as e:
        logger.error("Error updating Jira email for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception updating Jira email")
        return get_mongodb_error_message(e, "set_jira_email")


def show_jira_bug_query(team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    # Reuse get_settings so project-specific settings are applied if channel/project is set.
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        query = settings.get("jira_bug_query")

        if not query:
            return "Jira bug query is not set."

        return f"Current Jira bug query:\n```\n{query}\n```"
    except Exception as e:
        return get_mongodb_error_message(e, "show_jira_bug_query")


def set_jira_defaults(text: str, team_id: str, channel_id: str | None = None) -> str:
    """
    Set Jira default field values.
    Supports both single and multiple fields:
    - Single: set jira defaults project=PROJ-123
    - Multiple: set jira defaults project=PROJ-123 type=Bug priority=High
    """
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    payload = strip_command(text, "set jira defaults").strip()
    
    if not payload:
        return (
            "Please provide field=value pairs.\n"
            "Example: `set jira defaults project=PROJ-123 type=Bug priority=High`\n"
            "For a single field: `set jira defaults project=PROJ-123`"
        )
    
    # Parse field=value pairs
    pairs = payload.split()
    defaults = {}
    errors = []
    
    for pair in pairs:
        if '=' not in pair:
            errors.append(f"Invalid format: '{pair}' (expected field=value)")
            continue
        
        field_name, field_value = pair.split('=', 1)
        field_name = field_name.strip()
        field_value = field_value.strip()
        
        if not field_name:
            errors.append(f"Empty field name in: '{pair}'")
            continue
        
        if not field_value:
            errors.append(f"Empty field value in: '{pair}'")
            continue
        
        MAX_FIELD_NAME_LENGTH = 64
        if len(field_name) > MAX_FIELD_NAME_LENGTH:
            errors.append(f"Field name too long: '{field_name}' (max {MAX_FIELD_NAME_LENGTH} characters)")
            continue
        
        MAX_FIELD_VALUE_LENGTH = 512
        if len(field_value) > MAX_FIELD_VALUE_LENGTH:
            errors.append(f"Field value too long: '{field_value}' (max {MAX_FIELD_VALUE_LENGTH} characters)")
            continue
        
        defaults[field_name] = field_value
    
    if errors:
        return "Errors found:\n" + "\n".join(f"- {error}" for error in errors)
    
    if not defaults:
        return "No valid field=value pairs found."
    
    try:
        # Get current defaults and merge
        settings = get_settings(team_id, channel_id=channel_id)
        current_defaults = settings.get("jira_defaults", {})
        current_defaults.update(defaults)
        
        # Save back to settings
        logger.info(
            "Updating Jira defaults for team_id=%s, channel_id=%s, fields=%s",
            team_id, channel_id, list(defaults.keys())
        )
        logger.debug(
            "Jira defaults values for team_id=%s, channel_id=%s: %s",
            team_id, channel_id, defaults
        )
        _update_settings_field(team_id, channel_id, "jira_defaults", current_defaults)
        logger.info("Jira defaults updated successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        
        fields_list = ", ".join(f"*{k}*={v}" for k, v in defaults.items())
        return f"Jira defaults updated: {fields_list}."
    except Exception as e:
        logger.error("Error updating Jira defaults for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception updating Jira defaults")
        return get_mongodb_error_message(e, "set_jira_defaults")


def show_jira_defaults(team_id: str, channel_id: str | None = None) -> str:
    """
    Show all Jira default field values.
    """
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        defaults = settings.get("jira_defaults", {})
        
        if not defaults:
            return (
                "No Jira default fields are set.\n"
                "Use `set jira defaults field=value` to set fields.\n"
                "Example: `set jira defaults project=PROJ-123 type=Bug`"
            )
        
        lines = ["*Jira default fields:*"]
        for field_name, field_value in sorted(defaults.items()):
            lines.append(f"  • *{field_name}*: {field_value}")
        
        return "\n".join(lines)
    except Exception as e:
        return get_mongodb_error_message(e, "show_jira_defaults")


def clear_jira_default(text: str, team_id: str, channel_id: str | None = None) -> str:
    """
    Clear a specific Jira default field value.
    Syntax: clear jira default <field>
    Example: clear jira default project
    """
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    field_name = strip_command(text, "clear jira default").strip()
    
    if not field_name:
        return (
            "Please provide a field name to clear.\n"
            "Example: `clear jira default project`"
        )
    
    MAX_FIELD_NAME_LENGTH = 64
    if len(field_name) > MAX_FIELD_NAME_LENGTH:
        return f"Field name is too long (max {MAX_FIELD_NAME_LENGTH} characters)."
    
    try:
        # Get current defaults
        settings = get_settings(team_id, channel_id=channel_id)
        defaults = settings.get("jira_defaults", {})
        
        if field_name not in defaults:
            return f"Jira default field *{field_name}* is not set."
        
        # Remove the field
        del defaults[field_name]
        
        # Save back to settings (empty dict if no defaults left)
        logger.info(
            "Clearing Jira default field for team_id=%s, channel_id=%s, field=%s",
            team_id, channel_id, field_name
        )
        _update_settings_field(team_id, channel_id, "jira_defaults", defaults)
        logger.info("Jira default field cleared successfully for team_id=%s, channel_id=%s", team_id, channel_id)
        
        return f"Jira default field *{field_name}* has been cleared."
    except Exception as e:
        logger.error("Error clearing Jira default for team_id=%s, channel_id=%s, field=%s: %s", team_id, channel_id, field_name, str(e))
        logger.exception("Exception clearing Jira default")
        return get_mongodb_error_message(e, "clear_jira_default")


def _get_jira_client(team_id: str, channel_id: str | None = None) -> tuple[JIRA | None, str]:
    """
    Get a Jira client instance for the current project settings.
    Returns (JIRA client, error_message).
    If error_message is not empty, client will be None.
    """
    logger.debug("Getting Jira client for team_id=%s, channel_id=%s", team_id, channel_id)
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        
        jira_url = settings.get("jira_url", "").strip()
        jira_token = settings.get("jira_token", "").strip()
        jira_email = settings.get("jira_email", "").strip()
        
        logger.debug(
            "Jira settings check - URL present: %s, Token present: %s, Email present: %s",
            bool(jira_url), bool(jira_token), bool(jira_email)
        )
        
        # Check if required settings are configured
        missing = []
        if not jira_url:
            missing.append("Jira URL")
        if not jira_token:
            missing.append("Jira token")
        if not jira_email:
            missing.append("Jira email")
        
        if missing:
            missing_str = ", ".join(missing)
            logger.warning(
                "Jira configuration incomplete for team_id=%s, channel_id=%s. Missing: %s",
                team_id, channel_id, missing_str
            )
            return None, (
                f"Jira is not fully configured. Missing: {missing_str}.\n"
                f"Please set these using:\n"
                f"- `set jira url <url>`\n"
                f"- `set jira token <token>`\n"
                f"- `set jira email <email>`"
            )
        
        # Create Jira client with basic auth (email + API token)
        logger.debug("Attempting to create Jira client for URL: %s, Email: %s", jira_url, jira_email)
        try:
            jira = JIRA(
                server=jira_url,
                basic_auth=(jira_email, jira_token),
                timeout=10,
            )
            logger.info(
                "Jira client created successfully for team_id=%s, channel_id=%s, URL=%s",
                team_id, channel_id, jira_url
            )
            return jira, ""
        except JIRAError as e:
            logger.error(
                "Jira connection error for team_id=%s, channel_id=%s, URL=%s, status_code=%s, error=%s",
                team_id, channel_id, jira_url, e.status_code, e.text or str(e)
            )
            logger.exception("Jira connection error details for team_id=%s", team_id)
            if e.status_code == 401:
                return None, "Authentication failed. Please check your Jira email and token."
            elif e.status_code == 403:
                return None, "Access forbidden. Please check your Jira permissions."
            else:
                return None, f"Failed to connect to Jira: {e.text or str(e)}"
        except Exception as e:
            logger.error(
                "Unexpected error creating Jira client for team_id=%s, channel_id=%s, URL=%s, error=%s",
                team_id, channel_id, jira_url, str(e)
            )
            logger.exception("Unexpected error creating Jira client for team_id=%s", team_id)
            return None, f"Failed to connect to Jira: {str(e)}"
    except Exception as e:
        logger.error("Error in _get_jira_client for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception in _get_jira_client")
        return None, get_mongodb_error_message(e, "get_jira_client")


def test_jira_connection(team_id: str, channel_id: str | None = None) -> str:
    """
    Test the Jira connection for the current project.
    """
    logger.info("Testing Jira connection for team_id=%s, channel_id=%s", team_id, channel_id)
    
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        logger.debug("Project not set for team_id=%s, channel_id=%s", team_id, channel_id)
        return error_msg
    
    try:
        jira, error_msg = _get_jira_client(team_id, channel_id)
        
        if error_msg:
            logger.warning("Jira client creation failed for team_id=%s, channel_id=%s: %s", team_id, channel_id, error_msg)
            return error_msg
        
        # Test connection by fetching current user info
        logger.debug("Fetching current user info to test Jira connection")
        try:
            current_user = jira.current_user()
            logger.info(
                "Jira connection test successful for team_id=%s, channel_id=%s, user=%s",
                team_id, channel_id, current_user
            )
            return f"✅ Jira connection successful!\nConnected as: *{current_user}*"
        except JIRAError as e:
            logger.error(
                "Jira API error during connection test for team_id=%s, channel_id=%s, status_code=%s, error=%s",
                team_id, channel_id, e.status_code, e.text or str(e)
            )
            logger.exception("Jira API error during connection test for team_id=%s", team_id)
            if e.status_code == 401:
                return "❌ Authentication failed. Please check your Jira email and token."
            elif e.status_code == 403:
                return "❌ Access forbidden. Please check your Jira permissions."
            else:
                return f"❌ Jira connection test failed: {e.text or str(e)}"
        except Exception as e:
            logger.error(
                "Unexpected error testing Jira connection for team_id=%s, channel_id=%s, error=%s",
                team_id, channel_id, str(e)
            )
            logger.exception("Unexpected error testing Jira connection for team_id=%s", team_id)
            return f"❌ Jira connection test failed: {str(e)}"
    except Exception as e:
        logger.error("Exception in test_jira_connection for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception in test_jira_connection")
        return get_mongodb_error_message(e, "test_jira_connection")


def get_jira_bugs(team_id: str, channel_id: str | None = None) -> str:
    """
    Get list of Jira issues according to the JQL query specified in the current project.
    """
    logger.info("Fetching Jira bugs for team_id=%s, channel_id=%s", team_id, channel_id)
    
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        logger.debug("Project not set for team_id=%s, channel_id=%s", team_id, channel_id)
        return error_msg
    
    try:
        jira, error_msg = _get_jira_client(team_id, channel_id)
        
        if error_msg:
            logger.warning("Jira client creation failed for team_id=%s, channel_id=%s: %s", team_id, channel_id, error_msg)
            return error_msg
        
        # Get JQL query from project settings
        settings = get_settings(team_id, channel_id=channel_id)
        jql_query = settings.get("jira_bug_query", "").strip()
        
        if not jql_query:
            logger.warning("Jira bug query (JQL) not set for team_id=%s, channel_id=%s", team_id, channel_id)
            return (
                "Jira bug query (JQL) is not set for this project.\n"
                "Please set it using: `set jira query <JQL query>`\n"
                "Example: `set jira query project = PROJ AND status != Done`"
            )
        
        logger.debug("Executing JQL query for team_id=%s, channel_id=%s: %s", team_id, channel_id, jql_query)
        
        # Fetch issues using JQL
        try:
            # Limit to 50 issues to avoid overwhelming the response
            MAX_ISSUES = 50
            issues = jira.search_issues(jql_query, maxResults=MAX_ISSUES)
            
            logger.info(
                "Jira query executed successfully for team_id=%s, channel_id=%s. Found %s issue(s)",
                team_id, channel_id, len(issues)
            )
            
            if not issues:
                logger.debug("No issues found matching JQL query for team_id=%s, channel_id=%s", team_id, channel_id)
                return f"No issues found matching the query:\n```{jql_query}```"
            
            # Format issues for display
            lines = [f"Found *{len(issues)}* issue(s) (showing up to {MAX_ISSUES}):\n"]
            
            for issue in issues:
                # Get key fields
                key = issue.key
                summary = issue.fields.summary
                status = issue.fields.status.name
                issue_type = issue.fields.issuetype.name
                
                logger.debug("Processing issue %s: %s (%s, %s)", key, summary, issue_type, status)
                
                # Build issue URL
                jira_url = settings.get("jira_url", "").strip().rstrip('/')
                issue_url = f"{jira_url}/browse/{key}"
                
                lines.append(f"• *{key}*: {summary}")
                lines.append(f"  Type: {issue_type} | Status: {status}")
                lines.append(f"  <{issue_url}|View in Jira>")
                lines.append("")  # Empty line between issues
            
            if len(issues) == MAX_ISSUES:
                lines.append(f"\n_Note: Showing first {MAX_ISSUES} issues. There may be more._")
            
            return "\n".join(lines)
        except JIRAError as e:
            logger.error(
                "Jira API error fetching bugs for team_id=%s, channel_id=%s, JQL=%s, status_code=%s, error=%s",
                team_id, channel_id, jql_query, e.status_code, e.text or str(e)
            )
            logger.exception("Jira API error fetching bugs for team_id=%s", team_id)
            if e.status_code == 400:
                return (
                    f"❌ Invalid JQL query:\n```{jql_query}```\n"
                    f"Error: {e.text or str(e)}\n"
                    f"Please check your query syntax and try again."
                )
            elif e.status_code == 401:
                return "❌ Authentication failed. Please check your Jira email and token."
            elif e.status_code == 403:
                return "❌ Access forbidden. Please check your Jira permissions."
            else:
                return f"❌ Failed to fetch issues: {e.text or str(e)}"
        except Exception as e:
            logger.error(
                "Unexpected error fetching Jira bugs for team_id=%s, channel_id=%s, JQL=%s, error=%s",
                team_id, channel_id, jql_query, str(e)
            )
            logger.exception("Unexpected error fetching Jira bugs for team_id=%s", team_id)
            return f"❌ Failed to fetch issues: {str(e)}"
    except Exception as e:
        logger.error("Exception in get_jira_bugs for team_id=%s, channel_id=%s: %s", team_id, channel_id, str(e))
        logger.exception("Exception in get_jira_bugs")
        return get_mongodb_error_message(e, "get_jira_bugs")


def get_settings(team_id: str, channel_id: str | None = None):
    """
    Get project settings. bug_report_template and project_context are stored only in projects,
    not in settings. If channel_id is provided, returns project-specific settings.
    If channel_id is None, returns empty dict (for backward compatibility).
    
    Uses atomic MongoDB operations to prevent race conditions.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    if channel_id is not None:
        channel_id = sanitize_slack_id(channel_id, "channel_id", allow_none=False)
    
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

    try:
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
    except Exception as e:
        # Let exception propagate - calling functions will handle it
        raise
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

    # Sanitize project name to prevent MongoDB injection
    try:
        project_name = sanitize_project_name(project_name)
    except ValueError:
        logger.error(
            "Invalid project name in channel_projects for team_id=%s, channel_id=%s: %s",
            team_id,
            channel_id,
            project_name,
        )
        # Return defaults if project name is invalid
        return PROJECT_DEFAULTS

    # Get project-specific settings
    projects = org.get("projects") or {}
    project_settings = projects.get(project_name, {})

    # Merge with defaults
    merged_project_settings = {**PROJECT_DEFAULTS, **project_settings}

    # Persist back if something changed (safe migration / initialization)
    # Use atomic update to prevent race conditions
    if merged_project_settings != project_settings:
        try:
            orgs.update_one(
                {"team_id": team_id},
                {"$set": {f"projects.{project_name}": merged_project_settings}},
            )
        except Exception as e:
            # Let exception propagate - calling functions will handle it
            raise

    return merged_project_settings




def set_channel_project(text: str, team_id: str, channel_id: str) -> str:
    """
    Bind this Slack channel to a named project configuration within the org.
    If the project does not exist yet, it will be created with default project settings.
    Preserves welcome_shown flag in channel_projects for this channel if it exists.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    channel_id = sanitize_slack_id(channel_id, "channel_id")
    
    project_name = strip_command(text, "use project").strip()

    if not project_name:
        return (
            "Please provide a project name. Example:\n"
            "`use project Mobile app`"
        )

    # Sanitize project name to prevent MongoDB injection (dot notation, operators)
    try:
        project_name = sanitize_project_name(project_name)
    except ValueError as e:
        return f"Invalid project name: {str(e)}"

    # Store channel → project binding and preserve welcome_shown flag if it exists
    # channel_projects structure: {channel_id: {"project": project_name, "welcome_shown": bool}}
    # Preserve existing welcome_shown value if it exists, don't set it if it doesn't exist
    try:
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
    except Exception as e:
        return get_mongodb_error_message(e, "set_channel_project")


def list_projects(team_id: str) -> str:
    # Sanitize input to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    try:
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
    except Exception as e:
        return get_mongodb_error_message(e, "list_projects")


def get_channel_project_name(team_id: str, channel_id: str) -> str | None:
    """
    Get the project name bound to a channel from channel_projects.
    Returns None if channel is not bound to a project.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    channel_id = sanitize_slack_id(channel_id, "channel_id")
    try:
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
    except Exception as e:
        logger.exception("Error getting channel project name: %s", e)
        return None  # Return None on error to allow graceful degradation


def _require_project(team_id: str, channel_id: str | None) -> str | None:
    """
    Check if a project is set for the channel. Returns None if project is set,
    or an error message string if project is not set.
    """
    if channel_id is None:
        # No channel context, allow operation (might be used in DMs or fallback scenarios)
        return None
    
    project_name = get_channel_project_name(team_id, channel_id)
    if not project_name:
        return (
            "❌ No project is set for this channel.\n"
            "Please set a project first using: `use project <project-name>`\n"
            "Example: `use project Mobile app`"
        )
    return None


def get_channel_welcome_shown(team_id: str, channel_id: str) -> bool:
    """
    Get whether the welcome message has been shown for a channel from channel_projects.
    Returns False if not set or channel not found.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    channel_id = sanitize_slack_id(channel_id, "channel_id")
    try:
        org = orgs.find_one({"team_id": team_id}, {"channel_projects": 1})
        if not org:
            return False
        
        channel_projects = org.get("channel_projects") or {}
        channel_info = channel_projects.get(channel_id)
        
        if isinstance(channel_info, dict):
            return channel_info.get("welcome_shown", False)
        return False
    except Exception as e:
        logger.exception("Error getting channel welcome shown: %s", e)
        return False  # Return False on error to allow graceful degradation


def set_channel_welcome_shown(team_id: str, channel_id: str, value: bool) -> None:
    """
    Set whether the welcome message has been shown for a channel in channel_projects.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    channel_id = sanitize_slack_id(channel_id, "channel_id")
    try:
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {f"channel_projects.{channel_id}.welcome_shown": value}},
            upsert=True,
        )
    except Exception as e:
        logger.exception("Error setting channel welcome shown: %s", e)
        # Don't raise - this is a non-critical operation


def show_channel_status(team_id: str, channel_id: str | None) -> str:
    """
    Show the current channel status including project name, project context, use_project_context flag,
    Jira URL, and Jira token status.
    """
    if not channel_id:
        return "Channel status is only available when called from a channel."
    
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    channel_id = sanitize_slack_id(channel_id, "channel_id")
    
    try:
        project_name = get_channel_project_name(team_id, channel_id)
        settings = get_settings(team_id, channel_id=channel_id)
    except Exception as e:
        return get_mongodb_error_message(e, "show_channel_status")
    
    project_context = settings.get("project_context", "").strip()
    use_project_context = settings.get("use_project_context", False)
    jira_url = settings.get("jira_url", "").strip()
    jira_token = settings.get("jira_token", "").strip()
    jira_email = settings.get("jira_email", "").strip()
    jira_defaults = settings.get("jira_defaults", {})
    
    lines = []
    lines.append(f"*Project name:* {project_name if project_name else 'N/A'}")
    lines.append(f"*Project context:* {project_context if project_context else 'N/A'}")
    lines.append(f"*Use project context:* {use_project_context}")
    lines.append(f"*Jira URL:* {jira_url if jira_url else 'N/A'}")
    lines.append(f"*Jira token:* {'set' if jira_token else 'not set'}")
    lines.append(f"*Jira email:* {jira_email if jira_email else 'N/A'}")
    
    if jira_defaults:
        defaults_str = ", ".join(f"{k}={v}" for k, v in sorted(jira_defaults.items()))
        lines.append(f"*Jira defaults:* {defaults_str}")
    else:
        lines.append("*Jira defaults:* none")
    
    return "\n".join(lines)


def _update_settings_field(team_id: str, channel_id: str | None, field: str, value) -> None:
    """
    Update a configuration field. Project-specific fields (bug_report_template, project_context,
    use_project_context, jira_*) are stored in projects.
    
    If channel_id is provided and channel is bound to a project, update that project.
    If channel_id is None or channel is not bound to a project, create/use a default project
    for project-specific fields.
    """
    # Sanitize inputs to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    if channel_id is not None:
        channel_id = sanitize_slack_id(channel_id, "channel_id", allow_none=False)
    
    # Validate field name to prevent injection
    if not isinstance(field, str) or not field.strip():
        raise ValueError("Field name must be a non-empty string")
    
    # Fields that belong in projects
    PROJECT_FIELDS = {
        "bug_report_template",
        "project_context",
        "use_project_context",
        "jira_token",
        "jira_url",
        "jira_bug_query",
        "jira_email",
        "jira_defaults",
    }
    
    try:
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
                    # Sanitize project name to prevent MongoDB injection
                    try:
                        project_name = sanitize_project_name(project_name)
                    except ValueError:
                        logger.error(
                            "Invalid project name in channel_projects for team_id=%s, channel_id=%s: %s",
                            team_id,
                            channel_id,
                            project_name,
                        )
                        # Skip update if project name is invalid
                        return
                    
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
                # Sanitize project name to prevent MongoDB injection
                try:
                    project_name = sanitize_project_name(project_name)
                except ValueError:
                    logger.error(
                        "Invalid project name in channel_projects for team_id=%s, channel_id=%s: %s",
                        team_id,
                        channel_id,
                        project_name,
                    )
                    # Skip update if project name is invalid
                    return
                
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
    except Exception as e:
        # Let exception propagate - calling functions will handle it
        raise
