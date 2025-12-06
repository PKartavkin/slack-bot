"""
Configuration and environment variable validation.
"""
import os
import sys

from bot.logger import logger


def validate_environment_variables() -> None:
    """
    Validate all required environment variables at startup.
    Exits the application with a clear error message if any are missing.
    """
    required_vars = {
        "SLACK_BOT_TOKEN": "Slack bot token for authentication",
        "SLACK_SIGNING_SECRET": "Slack signing secret for request verification",
        "MONGO_URL": "MongoDB connection URL",
        "OPENAI_API_KEY": "OpenAI API key for bug report generation",
    }
    
    missing_vars = []
    
    for var_name, description in required_vars.items():
        value = os.getenv(var_name)
        if not value or not value.strip():
            missing_vars.append(f"  - {var_name}: {description}")
            logger.error(f"Missing required environment variable: {var_name}")
    
    if missing_vars:
        error_message = (
            "Missing required environment variables:\n"
            + "\n".join(missing_vars)
            + "\n\nPlease set these variables before starting the application."
        )
        logger.critical(error_message)
        print(error_message, file=sys.stderr)
        sys.exit(1)
    
    # Log rate limiting configuration
    rate_limit_max = int(os.getenv("RATE_LIMIT_OPENAI_MAX", "100"))
    logger.info(f"OpenAI rate limiting: {rate_limit_max} requests per organization per day")
    
    logger.info("Environment variable validation completed successfully")

