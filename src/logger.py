import logging
import sys

# Configure logging to write to stderr (unbuffered, better for containers)
# Railway captures both stdout and stderr, but stderr is unbuffered by default
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]  # Changed to stderr for unbuffered output
)

logger = logging.getLogger("slackbot")
