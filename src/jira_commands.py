"""
Jira integration commands for configuring and interacting with Jira.
"""
import unicodedata

from jira import JIRA
from jira.exceptions import JIRAError

from src.logger import logger
from src.utils import strip_command, get_mongodb_error_message
from src.constants import (
    JIRA_CLIENT_TIMEOUT_SECONDS,
    MAX_JIRA_TOKEN_LENGTH,
    MIN_JIRA_TOKEN_LENGTH,
    MAX_JIRA_URL_LENGTH,
    MAX_JIRA_QUERY_LENGTH,
    MIN_JIRA_QUERY_LENGTH,
    MAX_JIRA_EMAIL_LENGTH,
    MAX_JIRA_ISSUES_LIMIT,
    MAX_JIRA_FIELD_NAME_LENGTH,
    MAX_JIRA_FIELD_VALUE_LENGTH,
    HTTP_STATUS_BAD_REQUEST,
    HTTP_STATUS_UNAUTHORIZED,
    HTTP_STATUS_FORBIDDEN,
)
from src.project_commands import (
    _require_project,
    get_settings,
    _update_settings_field,
)


def set_jira_token(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    token = strip_command(text, "set jira token").strip()

    if not token:
        return "Please provide a Jira token. Example: `set jira token <your-token>`"

    if len(token) < MIN_JIRA_TOKEN_LENGTH:
        return "Jira token looks too short. Please send a valid token."

    if len(token) > MAX_JIRA_TOKEN_LENGTH:
        return (
            f"Jira token looks unusually long. "
            f"Please ensure it's correct and shorter than {MAX_JIRA_TOKEN_LENGTH} characters."
        )

    try:
        _update_settings_field(team_id, channel_id, "jira_token", token)
        return "Jira token has been updated."
    except Exception as e:
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
    # Replace non-breaking spaces with regular spaces, then strip once
    url = url.replace('\u00a0', ' ').strip()

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

    if len(url) > MAX_JIRA_URL_LENGTH:
        return (
            f"Jira URL is too long. "
            f"Please provide a URL shorter than {MAX_JIRA_URL_LENGTH} characters."
        )

    try:
        _update_settings_field(team_id, channel_id, "jira_url", url)
        return "Jira URL has been updated."
    except Exception as e:
        return get_mongodb_error_message(e, "set_jira_url")


def set_jira_bug_query(text: str, team_id: str, channel_id: str | None = None):
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    query = strip_command(text, "set jira query").strip()

    if not query:
        return "Please provide a JQL query. Example: `set jira query project = PROJ AND status != Done`"

    if len(query) < MIN_JIRA_QUERY_LENGTH:
        return "Jira query looks too short. Please provide a valid JQL query."

    if len(query) > MAX_JIRA_QUERY_LENGTH:
        return (
            f"Jira query is too long. "
            f"Please shorten it to under {MAX_JIRA_QUERY_LENGTH} characters."
        )

    try:
        _update_settings_field(team_id, channel_id, "jira_bug_query", query)
        return "Jira bug query has been updated."
    except Exception as e:
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

    if len(email) > MAX_JIRA_EMAIL_LENGTH:
        return (
            f"Jira email is too long. "
            f"Please provide an email shorter than {MAX_JIRA_EMAIL_LENGTH} characters."
        )

    try:
        _update_settings_field(team_id, channel_id, "jira_email", email)
        return "Jira email has been updated."
    except Exception as e:
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
        
        if len(field_name) > MAX_JIRA_FIELD_NAME_LENGTH:
            errors.append(f"Field name too long: '{field_name}' (max {MAX_JIRA_FIELD_NAME_LENGTH} characters)")
            continue
        
        if len(field_value) > MAX_JIRA_FIELD_VALUE_LENGTH:
            errors.append(f"Field value too long: '{field_value}' (max {MAX_JIRA_FIELD_VALUE_LENGTH} characters)")
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
        _update_settings_field(team_id, channel_id, "jira_defaults", current_defaults)
        
        fields_list = ", ".join(f"*{k}*={v}" for k, v in defaults.items())
        return f"Jira defaults updated: {fields_list}."
    except Exception as e:
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
    
    if len(field_name) > MAX_JIRA_FIELD_NAME_LENGTH:
        return f"Field name is too long (max {MAX_JIRA_FIELD_NAME_LENGTH} characters)."
    
    try:
        # Get current defaults
        settings = get_settings(team_id, channel_id=channel_id)
        defaults = settings.get("jira_defaults", {})
        
        if field_name not in defaults:
            return f"Jira default field *{field_name}* is not set."
        
        # Remove the field
        del defaults[field_name]
        
        # Save back to settings (empty dict if no defaults left)
        _update_settings_field(team_id, channel_id, "jira_defaults", defaults)
        
        return f"Jira default field *{field_name}* has been cleared."
    except Exception as e:
        return get_mongodb_error_message(e, "clear_jira_default")


def _get_jira_client(team_id: str, channel_id: str | None = None) -> tuple[JIRA | None, str]:
    """
    Get a Jira client instance for the current project settings.
    Returns (JIRA client, error_message).
    If error_message is not empty, client will be None.
    """
    try:
        settings = get_settings(team_id, channel_id=channel_id)
        
        jira_url = settings.get("jira_url", "").strip()
        jira_token = settings.get("jira_token", "").strip()
        jira_email = settings.get("jira_email", "").strip()
        
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
            return None, (
                f"Jira is not fully configured. Missing: {missing_str}.\n"
                f"Please set these using:\n"
                f"- `set jira url <url>`\n"
                f"- `set jira token <token>`\n"
                f"- `set jira email <email>`"
            )
        
        # Create Jira client with basic auth (email + API token)
        try:
            jira = JIRA(
                server=jira_url,
                basic_auth=(jira_email, jira_token),
                timeout=JIRA_CLIENT_TIMEOUT_SECONDS,
            )
            return jira, ""
        except JIRAError as e:
            logger.exception("Jira connection error for team_id=%s", team_id)
            if e.status_code == HTTP_STATUS_UNAUTHORIZED:
                return None, "Authentication failed. Please check your Jira email and token."
            elif e.status_code == HTTP_STATUS_FORBIDDEN:
                return None, "Access forbidden. Please check your Jira permissions."
            else:
                return None, f"Failed to connect to Jira: {e.text or str(e)}"
        except Exception as e:
            logger.exception("Unexpected error creating Jira client for team_id=%s", team_id)
            return None, f"Failed to connect to Jira: {str(e)}"
    except Exception as e:
        return None, get_mongodb_error_message(e, "get_jira_client")


def test_jira_connection(team_id: str, channel_id: str | None = None) -> str:
    """
    Test the Jira connection for the current project.
    """
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    try:
        jira, error_msg = _get_jira_client(team_id, channel_id)
        
        if error_msg:
            return error_msg
        
        # Test connection by fetching current user info
        try:
            current_user = jira.current_user()
            return f"✅ Jira connection successful!\nConnected as: *{current_user}*"
        except JIRAError as e:
            logger.exception("Jira API error during connection test for team_id=%s", team_id)
            if e.status_code == HTTP_STATUS_UNAUTHORIZED:
                return "❌ Authentication failed. Please check your Jira email and token."
            elif e.status_code == HTTP_STATUS_FORBIDDEN:
                return "❌ Access forbidden. Please check your Jira permissions."
            else:
                return f"❌ Jira connection test failed: {e.text or str(e)}"
        except Exception as e:
            logger.exception("Unexpected error testing Jira connection for team_id=%s", team_id)
            return f"❌ Jira connection test failed: {str(e)}"
    except Exception as e:
        return get_mongodb_error_message(e, "test_jira_connection")


def get_jira_bugs(team_id: str, channel_id: str | None = None) -> str:
    """
    Get list of Jira issues according to the JQL query specified in the current project.
    """
    # Check if project is required
    error_msg = _require_project(team_id, channel_id)
    if error_msg:
        return error_msg
    
    try:
        jira, error_msg = _get_jira_client(team_id, channel_id)
        
        if error_msg:
            return error_msg
        
        # Get JQL query from project settings
        settings = get_settings(team_id, channel_id=channel_id)
        jql_query = settings.get("jira_bug_query", "").strip()
        
        if not jql_query:
            return (
                "Jira bug query (JQL) is not set for this project.\n"
                "Please set it using: `set jira query <JQL query>`\n"
                "Example: `set jira query project = PROJ AND status != Done`"
            )
        
        # Fetch issues using JQL
        try:
            # Limit to avoid overwhelming the response
            issues = jira.search_issues(jql_query, maxResults=MAX_JIRA_ISSUES_LIMIT)
            
            if not issues:
                return f"No issues found matching the query:\n```{jql_query}```"
            
            # Format issues for display
            lines = [f"Found *{len(issues)}* issue(s) (showing up to {MAX_JIRA_ISSUES_LIMIT}):\n"]
            
            for issue in issues:
                # Get key fields
                key = issue.key
                summary = issue.fields.summary
                status = issue.fields.status.name
                issue_type = issue.fields.issuetype.name
                
                # Build issue URL
                jira_url = settings.get("jira_url", "").strip().rstrip('/')  # strip() then rstrip() is intentional
                issue_url = f"{jira_url}/browse/{key}"
                
                lines.append(f"• *{key}*: {summary}")
                lines.append(f"  Type: {issue_type} | Status: {status}")
                lines.append(f"  <{issue_url}|View in Jira>")
                lines.append("")  # Empty line between issues
            
            if len(issues) == MAX_JIRA_ISSUES_LIMIT:
                lines.append(f"\n_Note: Showing first {MAX_JIRA_ISSUES_LIMIT} issues. There may be more._")
            
            return "\n".join(lines)
        except JIRAError as e:
            logger.exception("Jira API error fetching bugs for team_id=%s", team_id)
            if e.status_code == HTTP_STATUS_BAD_REQUEST:
                return (
                    f"❌ Invalid JQL query:\n```{jql_query}```\n"
                    f"Error: {e.text or str(e)}\n"
                    f"Please check your query syntax and try again."
                )
            elif e.status_code == HTTP_STATUS_UNAUTHORIZED:
                return "❌ Authentication failed. Please check your Jira email and token."
            elif e.status_code == HTTP_STATUS_FORBIDDEN:
                return "❌ Access forbidden. Please check your Jira permissions."
            else:
                return f"❌ Failed to fetch issues: {e.text or str(e)}"
        except Exception as e:
            logger.exception("Unexpected error fetching Jira bugs for team_id=%s", team_id)
            return f"❌ Failed to fetch issues: {str(e)}"
    except Exception as e:
        return get_mongodb_error_message(e, "get_jira_bugs")
