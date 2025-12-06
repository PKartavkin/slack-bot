import logging
import sys

# Configure logging to write to stderr (unbuffered, better for containers)
# Railway captures both stdout and stderr, but stderr is unbuffered by default
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]  # Changed to stderr for unbuffered output
)

# Suppress verbose pymongo DEBUG logs (topology, connection pool, etc.)
# Set pymongo loggers to INFO level to reduce noise
logging.getLogger("pymongo").setLevel(logging.INFO)
logging.getLogger("pymongo.topology").setLevel(logging.INFO)
logging.getLogger("pymongo.connection").setLevel(logging.INFO)
logging.getLogger("pymongo.serverSelection").setLevel(logging.INFO)

logger = logging.getLogger("slackbot")
