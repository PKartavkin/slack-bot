from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError
import os

from src.logger import logger

try:
    mongo_url = os.environ.get("MONGO_URL")
    if not mongo_url:
        raise ValueError("MONGO_URL environment variable is not set")
    
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
    # Test the connection
    client.admin.command('ping')
    db = client["slackbot"]
    orgs = db["organizations"]
    logger.info("MongoDB connection established successfully")
except (ConnectionFailure, ConfigurationError, ValueError) as e:
    logger.critical("Failed to connect to MongoDB: %s", e)
    raise
except Exception as e:
    logger.critical("Unexpected error connecting to MongoDB: %s", e)
    raise
