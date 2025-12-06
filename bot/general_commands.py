"""
General utility commands like help.
"""
from bot.logger import logger


def get_help() -> str:
    logger.debug("Help")
    return """
    *Available commands:*
    
    *General:*
    `help` - show this help message
    `status` - show current channel status and project configuration
    
    *Project Management:*
    `list projects` - list all available project configurations
    `use project <name>` - bind channel to a project configuration
    
    *Bug Reports:*
    `create bug report` - format your message into a structured bug report
    `show bug template` - show the current bug report template
    `edit bug template` - edit the bug report template
    
    *Documentation:*
    `show project` - display project documentation/overview
    `update docs` - update project documentation
    `enable docs` - enable using project docs for bug reports
    `disable docs` - disable using project docs for bug reports
    
    *Jira Configuration:*
    `set jira token <token>` - set Jira API token
    `set jira url <url>` - set Jira instance URL
    `set jira email <email>` - set Jira email address
    `set jira query <JQL>` - set JQL query for fetching bugs
    `show jira query` - show current Jira JQL query
    
    *Jira Default Fields:*
    `set jira defaults field=value` - set Jira default field values (supports multiple: field1=value1 field2=value2)
    `show jira defaults` - show all Jira default field values
    `clear jira default <field>` - clear a Jira default field value
    
    *Jira Operations:*
    `test jira` - test Jira connection for current project
    `get bugs` - get list of Jira issues using the configured JQL query
    """
