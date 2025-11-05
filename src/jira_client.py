# jira_client.py
import os
from jira import JIRA
from typing import List, Tuple, Optional

from src.logger import logger


def _connect() -> Tuple[Optional[JIRA], Optional[str]]:
    jira_url = os.environ.get("JIRA_URL")
    jira_email = os.environ.get("JIRA_EMAIL")
    jira_token = os.environ.get("JIRA_API_TOKEN")

    if not all([jira_url, jira_email, jira_token]):
        return None, "Missing JIRA_URL, JIRA_EMAIL, or JIRA_API_TOKEN."

    try:
        jira = JIRA(
            server=jira_url,
            basic_auth=(jira_email, jira_token)
        )
        return jira, None
    except Exception as e:
        return None, f"Failed to connect: {e}"

def get_open_bugs_from_epic() -> Tuple[Optional[List[str]], Optional[str]]:
    epic_id = os.environ.get("EPIC_KEY")
    if not epic_id:
        return None, "Missing EPIC_KEY in environment."

    jira, err = _connect()
    if err:
        return None, err

    # Corrected JQL: find bugs whose parent is the epic and are To Do
    #todo-delete
    #jql = f'parent = "{epic_id}" AND status = "To Do" AND issuetype = Bug'
    jql = 'issuetype = Bug'
    logger.debug(f'JQL: {jql}')

    try:
        issues = jira.search_issues(jql, maxResults=10, fields="*all")
        ####
        # Log raw JSON from Jira
        logger.debug(f"Raw issue: {issues}")
        for issue in issues:
            print(issue.key, issue.fields.__dict__)  # inspect fields
        ####
    except Exception as e:
        return None, f"Jira search error: {e}"

    jira_url = os.environ["JIRA_URL"].rstrip("/")
    results = []

    for issue in issues:
        key = issue.key
        summary = issue.fields.summary
        link = f"{jira_url}/browse/{key}"
        results.append(f"{key}: {summary} – {link}")

    return results, None
