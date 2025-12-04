import re


def contains(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)

def strip_command(text: str, command: str) -> str:
    """
    Remove the command phrase from text and return the remaining payload.
    Handles case-insensitive matching and ensures clean extraction.
    
    Args:
        text: The full text (should already have bot mention removed)
        command: The command phrase to remove (case-insensitive)
        
    Returns:
        The text with the command phrase removed, stripped of whitespace
    """
    if not text or not command:
        return text.strip() if text else ""
    
    # Normalize both to lowercase for finding, but DON'T strip text yet
    # We need to preserve the original positions
    lowered_text = text.lower()
    lowered_command = command.lower().strip()
    
    # Find the command in the text (case-insensitive)
    idx = lowered_text.find(lowered_command)
    if idx == -1:
        # Command not found, return original text stripped
        return text.strip()
    
    # Calculate where the command ends in the original text
    # The positions align because we're doing case-insensitive matching
    command_end = idx + len(command)
    
    # Extract everything after the command and immediately remove leading whitespace
    after = text[command_end:].lstrip()
    
    # Get everything before the command (in case there's extra text)
    before = text[:idx]
    
    # Combine - before should be empty if command is at start, after is already stripped
    cleaned = (before + after).strip()
    
    return cleaned


def strip_leading_mention(text: str) -> str:
    """
    Remove a leading Slack user mention like '<@U123ABC>' plus any following whitespace.
    This helps us reason about the actual user message length and content.
    """
    return re.sub(r"^<@[^>]+>\s*", "", text or "").strip()


def sanitize_slack_id(identifier: str | None, name: str = "identifier", allow_none: bool = False) -> str | None:
    """
    Sanitize and validate Slack IDs (team_id, channel_id, user_id).
    
    Slack IDs are typically uppercase alphanumeric strings, but we allow
    lowercase and common separators for robustness. Rejects MongoDB operators
    and special characters that could be used for injection.
    
    Args:
        identifier: The ID to sanitize
        name: Name of the identifier for error messages
        allow_none: If True, return None for None input instead of raising error
        
    Returns:
        Sanitized identifier (or None if allow_none=True and input is None)
        
    Raises:
        ValueError: If identifier is invalid or contains dangerous characters
    """
    if identifier is None:
        if allow_none:
            return None
        raise ValueError(f"{name} cannot be None")
    
    if not identifier:
        raise ValueError(f"{name} cannot be empty")
    
    if not isinstance(identifier, str):
        raise ValueError(f"{name} must be a string, got {type(identifier).__name__}")
    
    # Remove whitespace
    identifier = identifier.strip()
    
    if not identifier:
        raise ValueError(f"{name} cannot be empty after stripping whitespace")
    
    # Check for MongoDB operators that could be used for injection
    # These patterns indicate potential operator injection attempts
    dangerous_patterns = [
        r'\$[a-z]+',  # MongoDB operators like $gt, $ne, $regex
        r'^\$',       # Starting with $
        r'\{',        # Object notation
        r'\}',        # Object notation
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, identifier, re.IGNORECASE):
            raise ValueError(
                f"{name} contains invalid characters that could be used for injection: {identifier}"
            )
    
    # Allow alphanumeric, hyphens, underscores (Slack ID format)
    # Slack IDs are typically uppercase alphanumeric, but we're lenient
    if not re.match(r'^[A-Za-z0-9_-]+$', identifier):
        raise ValueError(
            f"{name} contains invalid characters. "
            f"Only alphanumeric characters, hyphens, and underscores are allowed: {identifier}"
        )
    
    # Reasonable length limit
    MAX_ID_LENGTH = 256
    if len(identifier) > MAX_ID_LENGTH:
        raise ValueError(f"{name} is too long (max {MAX_ID_LENGTH} characters): {len(identifier)}")
    
    return identifier


def sanitize_project_name(project_name: str) -> str:
    """
    Sanitize and validate project names to prevent MongoDB injection.
    
    Project names are used in dot-notation field paths like "projects.{name}.field",
    so they must not contain dots (.) or MongoDB operators ($).
    
    Args:
        project_name: The project name to sanitize
        
    Returns:
        Sanitized project name
        
    Raises:
        ValueError: If project name is invalid or contains dangerous characters
    """
    if not project_name:
        raise ValueError("Project name cannot be None or empty")
    
    if not isinstance(project_name, str):
        raise ValueError(f"Project name must be a string, got {type(project_name).__name__}")
    
    # Remove leading/trailing whitespace
    project_name = project_name.strip()
    
    if not project_name:
        raise ValueError("Project name cannot be empty after stripping whitespace")
    
    # Check for dangerous characters that could be used for MongoDB injection
    # Dots (.) are dangerous because they're used in dot notation for nested fields
    # Dollar signs ($) are MongoDB operators
    if '.' in project_name:
        raise ValueError(
            "Project name cannot contain dots (.) as they are used for MongoDB field paths. "
            f"Invalid name: {project_name}"
        )
    
    if '$' in project_name:
        raise ValueError(
            "Project name cannot contain dollar signs ($) as they are MongoDB operators. "
            f"Invalid name: {project_name}"
        )
    
    # Check for MongoDB operators in the name
    if re.search(r'\$[a-z]+', project_name, re.IGNORECASE):
        raise ValueError(
            f"Project name contains MongoDB operators: {project_name}"
        )
    
    # Check for object notation
    if '{' in project_name or '}' in project_name:
        raise ValueError(
            "Project name cannot contain braces ({}). "
            f"Invalid name: {project_name}"
        )
    
    # Reasonable length limit (already checked in set_channel_project, but enforce here too)
    MAX_PROJECT_NAME_LENGTH = 128
    if len(project_name) > MAX_PROJECT_NAME_LENGTH:
        raise ValueError(
            f"Project name is too long (max {MAX_PROJECT_NAME_LENGTH} characters): {len(project_name)}"
        )
    
    return project_name


def get_mongodb_error_message(error: Exception, operation_name: str = "operation") -> str:
    """
    Convert MongoDB errors to user-friendly messages.
    
    Args:
        error: The exception that occurred
        operation_name: Name of the operation for logging context
        
    Returns:
        User-friendly error message string
    """
    from pymongo.errors import (
        ConnectionFailure,
        ServerSelectionTimeoutError,
        OperationFailure,
        PyMongoError,
    )
    from src.logger import logger
    
    logger.exception("MongoDB error in %s: %s", operation_name, str(error))
    
    # Provide specific error messages based on error type
    if isinstance(error, (ConnectionFailure, ServerSelectionTimeoutError)):
        return (
            "I'm having trouble connecting to the database. "
            "Please try again in a moment."
        )
    elif isinstance(error, OperationFailure):
        return (
            "A database operation failed. "
            "Please try again or contact support if the issue persists."
        )
    elif isinstance(error, PyMongoError):
        return (
            "A database error occurred. "
            "Please try again in a moment."
        )
    else:
        # For non-MongoDB errors that might occur, use generic message
        return (
            "An unexpected error occurred while accessing the database. "
            "Please try again or contact support."
        )
