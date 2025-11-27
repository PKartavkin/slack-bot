import os
from openai import OpenAI
from src.db import orgs
from src.logger import logger

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def generate_bug_report(text: str, team_id: str) -> str:
    logger.debug("Creating formatting")
    settings = get_settings(team_id)
    context_block = settings["project_context"] if settings["use_project_context"] else ""
    prompt = f"""
    Convert the user's message into a bug report.

    {context_block}

    Use the following format exactly:
    {settings['bug_report_template']}

    Rules:
    - If project context is disabled or empty, ignore it.
    - Bug name must be short (3–6 words).
    - Steps must be numbered and reproducible.
    - Infer details only when logically obvious.
    - If the user input is too short to create a meaningful bug report, respond with: "Too short for bug report".
    - Output only the bug report in the template format.

    User input: {text}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


def show_bug_report_template(team_id) -> str:
    logger.debug("Show bug report template")
    settings = get_settings(team_id)
    return settings["bug_report_template"]


def edit_bug_report_template(text: str, team_id: str) -> str:
    logger.debug("Editing bug report template")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.bug_report_template": text}},
        upsert=True
    )
    return "Bug report template updated"


def show_project_overview(team_id: str) -> str:
    logger.debug("Show project overview")
    settings = get_settings(team_id)
    return settings["project_context"]


def update_project_overview(text: str, team_id: str) -> str:
    logger.debug("Updating project overview")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.project_context": text}},
        upsert=True
    )
    return "Project overview updated."


def set_use_documentation(flag: bool, team_id) -> str:
    logger.debug(f"Use documentation flag: {flag}")
    orgs.update_one(
        {"team_id": team_id},
        {"$set": {"settings.use_project_context": flag}},
        upsert=True
    )
    return f"Use documentation: {flag}"


def get_help() -> str:
    logger.debug("Help")
    return """
    **Available commands:**
    **create bug report** - formats your input according to the template using knowledge about your project
    **show bug report** - shows template for bug reports
    **edit bug report**
    **about project** - displays information about your project
    **update docs**
    **use docs** - bot will used project documentation for bug reports
    **ignore docs** - bot will ignore docs
    """

def get_settings(team_id: str):
    org = orgs.find_one({"team_id": team_id})
    if not org or "settings" not in org:
        return {
            "use_project_context": False,
            "project_context": "",
            "bug_report_template": """
Bug name:
Steps:
Actual result:
Expected:
"""
        }
    return org["settings"]