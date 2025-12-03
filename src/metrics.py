from datetime import datetime

from .db import orgs
from .utils import sanitize_slack_id

def init_or_get_org(team_id: str) -> dict:
    """
    Get organization record from DB. If it doesn't exist, create it.
    """
    # Sanitize input to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    org = orgs.find_one({"team_id": team_id})
    if not org:
        # Create new org with initial metrics and joined_date (as ISO string)
        joined_date_str = datetime.utcnow().isoformat() + "Z"
        org = {
            "team_id": team_id,
            "bot_invocations_total": 0,
            "joined_date": joined_date_str,
        }
        orgs.insert_one(org)
        return org

    # Backfill joined_date for existing orgs (convert to string if needed)
    if "joined_date" not in org:
        joined_date_str = datetime.utcnow().isoformat() + "Z"
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {"joined_date": joined_date_str}},
        )
        org["joined_date"] = joined_date_str
    elif isinstance(org.get("joined_date"), datetime):
        # Convert existing datetime to ISO string
        joined_date_str = org["joined_date"].isoformat() + "Z"
        orgs.update_one(
            {"team_id": team_id},
            {"$set": {"joined_date": joined_date_str}},
        )
        org["joined_date"] = joined_date_str

    return org

def increment_bot_invocations(team_id: str):
    """
    Increment bot invocation counter for this org.
    """
    # Sanitize input to prevent MongoDB injection
    team_id = sanitize_slack_id(team_id, "team_id")
    # Atomically increment counter
    orgs.update_one(
        {"team_id": team_id},
        {"$inc": {"bot_invocations_total": 1}},
        upsert=True  # ensures record exists even if first call
    )

def get_bot_invocations(team_id: str) -> int:
    """
    Return total bot invocations for this org.
    """
    # Sanitization happens in init_or_get_org
    org = init_or_get_org(team_id)
    return org.get("bot_invocations_total", 0)
