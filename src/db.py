from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError
import os

from src.logger import logger
from src.constants import MONGODB_SERVER_SELECTION_TIMEOUT_MS

try:
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        raise ValueError("MONGO_URL environment variable is not set")
    
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=MONGODB_SERVER_SELECTION_TIMEOUT_MS)
    # Test the connection
    client.admin.command('ping')
    db = client["slackbot"]
    orgs = db["organizations"]
    rate_limits = db["rate_limits"]  # Separate collection for rate limiting
    
    # Create index on rate_limit_key for better query performance
    try:
        rate_limits.create_index("rate_limit_key", unique=True)
        logger.debug("Rate limits collection index created/verified")
    except Exception as e:
        logger.warning("Could not create index on rate_limits collection: %s", e)
    
    logger.info("MongoDB connection established successfully")
except (ConnectionFailure, ConfigurationError, ValueError) as e:
    logger.critical("Failed to connect to MongoDB: %s", e)
    raise
except Exception as e:
    logger.critical("Unexpected error connecting to MongoDB: %s", e)
    raise
