"""
Rate limiting implementation using MongoDB for persistence.
Uses sliding window algorithm for daily rate limiting.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from pymongo.errors import PyMongoError

from bot.db import rate_limits
from bot.logger import logger
from bot.utils import sanitize_slack_id


class RateLimiter:
    """
    Rate limiter using sliding window algorithm with MongoDB storage.
    Tracks requests per organization (team_id) with daily limits.
    """
    
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        operation_name: str = "default"
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_requests: Maximum number of requests allowed in the window
            window_seconds: Time window in seconds
            operation_name: Name of the operation being rate limited
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.operation_name = operation_name
    
    def _get_rate_limit_key(self, team_id: str) -> str:
        """Generate a unique key for rate limiting per organization."""
        return f"{self.operation_name}:{team_id}"
    
    def is_allowed(self, team_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            team_id: Slack team ID (organization identifier)
            
        Returns:
            Tuple of (is_allowed: bool, error_message: Optional[str])
        """
        try:
            # Sanitize input
            team_id = sanitize_slack_id(team_id, "team_id")
            
            key = self._get_rate_limit_key(team_id)
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=self.window_seconds)
            
            # Get or create rate limit document
            rate_limit_doc = rate_limits.find_one({"rate_limit_key": key})
            
            if not rate_limit_doc:
                # First request - create document
                rate_limits.insert_one({
                    "rate_limit_key": key,
                    "team_id": team_id,
                    "requests": [now],
                    "created_at": now,
                    "updated_at": now,
                })
                return True, None
            
            # Clean old requests outside the window
            requests = rate_limit_doc.get("requests", [])
            # Filter out requests older than window_start
            # Handle both datetime objects and ISO strings
            valid_requests = []
            for req in requests:
                if isinstance(req, datetime):
                    if req >= window_start:
                        valid_requests.append(req)
                elif isinstance(req, str):
                    # Try to parse ISO string
                    try:
                        req_dt = datetime.fromisoformat(req.replace('Z', '+00:00'))
                        if req_dt >= window_start:
                            valid_requests.append(req_dt)
                    except (ValueError, AttributeError):
                        # Skip invalid date strings
                        continue
            
            # Check if limit exceeded
            if len(valid_requests) >= self.max_requests:
                # Calculate time until oldest request expires
                if valid_requests:
                    oldest_request = min(valid_requests)
                    reset_time = oldest_request + timedelta(seconds=self.window_seconds)
                    time_until_reset = (reset_time - now).total_seconds()
                    
                    if time_until_reset > 0:
                        # Convert to hours and minutes for better readability
                        hours = int(time_until_reset // 3600)
                        minutes = int((time_until_reset % 3600) // 60)
                        
                        if hours > 0:
                            wait_msg = f"{hours} hour{'s' if hours != 1 else ''}"
                            if minutes > 0:
                                wait_msg += f" and {minutes} minute{'s' if minutes != 1 else ''}"
                        else:
                            wait_msg = f"{minutes} minute{'s' if minutes != 1 else ''}"
                        
                        return False, (
                            f"You've reached the daily limit of {self.max_requests} AI requests. "
                            f"Please try again in {wait_msg}. "
                            f"(Limit resets daily)"
                        )
            
            # Add current request
            valid_requests.append(now)
            
            # Update document
            rate_limits.update_one(
                {"rate_limit_key": key},
                {
                    "$set": {
                        "requests": valid_requests,
                        "updated_at": now,
                    }
                }
            )
            
            return True, None
            
        except PyMongoError as e:
            logger.exception("MongoDB error in rate limiter for team_id=%s: %s", team_id, e)
            # On database error, allow the request (fail open)
            return True, None
        except Exception as e:
            logger.exception("Unexpected error in rate limiter for team_id=%s: %s", team_id, e)
            # On unexpected error, allow the request (fail open)
            return True, None
    
    def get_remaining_requests(self, team_id: str) -> int:
        """
        Get number of remaining requests in current window.
        
        Args:
            team_id: Slack team ID
            
        Returns:
            Number of remaining requests
        """
        try:
            team_id = sanitize_slack_id(team_id, "team_id")
            
            key = self._get_rate_limit_key(team_id)
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=self.window_seconds)
            
            rate_limit_doc = rate_limits.find_one({"rate_limit_key": key})
            if not rate_limit_doc:
                return self.max_requests
            
            requests = rate_limit_doc.get("requests", [])
            # Filter valid requests
            valid_requests = []
            for req in requests:
                if isinstance(req, datetime):
                    if req >= window_start:
                        valid_requests.append(req)
                elif isinstance(req, str):
                    try:
                        req_dt = datetime.fromisoformat(req.replace('Z', '+00:00'))
                        if req_dt >= window_start:
                            valid_requests.append(req_dt)
                    except (ValueError, AttributeError):
                        continue
            
            return max(0, self.max_requests - len(valid_requests))
        except Exception as e:
            logger.exception("Error getting remaining requests for team_id=%s: %s", team_id, e)
            return self.max_requests  # Fail open


# Pre-configured rate limiter for OpenAI API calls
# Configurable via environment variables, defaults to 100 requests per organization per day
RATE_LIMIT_OPENAI_MAX = int(os.getenv("RATE_LIMIT_OPENAI_MAX", "100"))
RATE_LIMIT_OPENAI_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_OPENAI_WINDOW_SECONDS", "86400"))  # 24 hours

openai_rate_limiter = RateLimiter(
    max_requests=RATE_LIMIT_OPENAI_MAX,
    window_seconds=RATE_LIMIT_OPENAI_WINDOW_SECONDS,
    operation_name="openai_api"
)

