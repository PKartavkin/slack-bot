"""
Commands module - re-exports all command functions for backward compatibility.
This module has been split into smaller modules:
- project_commands.py: Project and settings management
- bug_report_commands.py: Bug report generation and templates
- jira_commands.py: Jira integration
- general_commands.py: General utility commands

All functions are re-exported here to maintain backward compatibility.
"""
# Re-export all functions from the split modules
from src.project_commands import (
    get_settings,
    set_channel_project,
    list_projects,
    get_channel_project_name,
    _require_project,
    get_channel_welcome_shown,
    set_channel_welcome_shown,
    show_channel_status,
    _update_settings_field,
)

from src.bug_report_commands import (
    generate_bug_report,
    show_bug_report_template,
    edit_bug_report_template,
    show_project_overview,
    update_project_overview,
    set_use_documentation,
)

from src.jira_commands import (
    set_jira_token,
    set_jira_url,
    set_jira_bug_query,
    show_jira_bug_query,
    set_jira_email,
    set_jira_defaults,
    show_jira_defaults,
    clear_jira_default,
    test_jira_connection,
    get_jira_bugs,
    _get_jira_client,
)

from src.general_commands import (
    get_help,
)

__all__ = [
    # Project commands
    "get_settings",
    "set_channel_project",
    "list_projects",
    "get_channel_project_name",
    "_require_project",
    "get_channel_welcome_shown",
    "set_channel_welcome_shown",
    "show_channel_status",
    "_update_settings_field",
    # Bug report commands
    "generate_bug_report",
    "show_bug_report_template",
    "edit_bug_report_template",
    "show_project_overview",
    "update_project_overview",
    "set_use_documentation",
    # Jira commands
    "set_jira_token",
    "set_jira_url",
    "set_jira_bug_query",
    "show_jira_bug_query",
    "set_jira_email",
    "set_jira_defaults",
    "show_jira_defaults",
    "clear_jira_default",
    "test_jira_connection",
    "get_jira_bugs",
    "_get_jira_client",
    # General commands
    "get_help",
]
