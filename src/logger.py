# bot/logger.py
import logging
import sys

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,           # Change to INFO in production
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("slackbot")
