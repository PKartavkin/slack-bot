"""
Project and settings management commands.
Core functions for managing projects, channels, and settings.
"""
from datetime import datetime

from bot.db import orgs
from bot.logger import logger
from bot.utils import (
    strip_command,
    sanitize_slack_id,
    sanitize_project_name,
    get_mongodb_error_message,
)


def _extract_and_sanitize_project_name(channel_info) -> str | None:
    """
    Extract and sanitize project name from channel_info.
    Handles both old format (channel_id -> project_name) and new format (channel_id -> {project: name}).
    
    Args:
        channel_info: The channel info from channel_projects dict (can be str or dict)
        
    Returns:
        Sanitized project name, or None if invalid/not found
    """
    # Handle both old format (channel_id -> project_name) and new format (channel_id -> {project: name})
    project_name = channel_info.get("project") if isinstance(channel_info, dict) else channel_info
    
    if not project_name:
        return None
    
    # Sanitize project name to prevent MongoDB injection
    try:
        return sanitize_project_name(project_name)
    except ValueError:
        logger.error("Invalid project name in channel_projects: %s", project_name)
        return None


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
        # Optimized: Combine multiple updates into fewer operations
        # First, ensure org exists and has required fields
        joined_date_str = datetime.utcnow().isoformat() + "Z"
        
        # Single update to ensure org exists with all required fields
        # $setOnInsert only sets these fields if document is being created
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
        
        # Fetch org once to check current state
        org = orgs.find_one({"team_id": team_id})
        
        # Handle all updates in a single operation if needed
        if org:
            needs_update = False
            update_fields = {}
            
            # Ensure channel_projects exists (only if missing)
            if "channel_projects" not in org:
                update_fields["channel_projects"] = {}
                needs_update = True
            
            # Check if joined_date needs conversion or backfill
            joined_date = org.get("joined_date")
            if not joined_date:
                # Backfill missing joined_date
                update_fields["joined_date"] = joined_date_str
                needs_update = True
            elif isinstance(joined_date, datetime):
                # Convert datetime to ISO string
                update_fields["joined_date"] = joined_date.isoformat() + "Z"
                needs_update = True
            
            # Perform single update if needed
            if needs_update:
                orgs.update_one(
                    {"team_id": team_id},
                    {"$set": update_fields},
                )
                # Update local org dict to avoid refetch
                org.update(update_fields)
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
    
    # Extract and sanitize project name
    project_name = _extract_and_sanitize_project_name(channel_info)

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
    Note: This returns the raw project name without sanitization (for backward compatibility).
    Use _extract_and_sanitize_project_name() if you need sanitized project names.
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
                
                # Extract and sanitize project name
                project_name = _extract_and_sanitize_project_name(channel_info)
                
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
            
            # Extract and sanitize project name
            project_name = _extract_and_sanitize_project_name(channel_info)
                
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
    except Exception as e:
        # Let exception propagate - calling functions will handle it
        raise
