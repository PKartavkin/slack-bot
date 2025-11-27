from .db import orgs

def init_or_get_org(team_id: str) -> dict:
    """
    Get organization record from DB. If it doesn't exist, create it.
    """
    org = orgs.find_one({"team_id": team_id})
    if not org:
        # Create new org with initial metrics
        org = {"team_id": team_id, "bot_invocations_total": 0}
        orgs.insert_one(org)
    return org

def increment_bot_invocations(team_id: str):
    """
    Increment bot invocation counter for this org.
    """
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
    org = init_or_get_org(team_id)
    return org.get("bot_invocations_total", 0)
