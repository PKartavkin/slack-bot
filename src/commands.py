import os
from openai import OpenAI
from src.logger import logger

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

use_project_context = False

project_context = """Optional project context:
Chatbot platform with multi-space architecture.

Organizations may include:
- Content Bot: manages content shared to other bots.
- Virtual Assistants (VA): custom behaviors per VA.
- Institution (sub-organization): may have a VA.

VA terms:
- Custom Questions: user-defined, used in chatbot flows. Flows can include additional questions, videos, Live Chat triggers, forms, and authentication.
- Global Questions (Content Pack): inherited from Content Bot; can be overridden.
- Canned Responses: predefined text for Live Conversations.
- System Variables: dynamic data used in questions and responses.
- Live Conversation: user-operator chat.
- SMS: message sending.
- Campaigns: mass messaging with configurable flows.
- Analytics: bot usage metrics.
- User Role: Internal (Admin, System) or Regular (Live Agent, User, Guest, Custom).
- Threat Detection: detects concerning messages.

System components:
- Bot Client: user-facing web or embedded interface.
- Sandbox: test bot client in Admin Panel.
- Admin Panel: content management, transcripts review, Live Chat, SMS.
- System Settings: bot configuration, tokens, notifications.
- Organization Pages: lists of VAs, members, and analytics.
- Organization Settings: logo, name, custom roles, feature toggles.
- Features: can be enabled or disabled per organization (Brain Crawler, Brain Files, SMS, Live Chat, System Variables, Global Questions).

Quick Facts:
- Most pages have a Filter panel and an Export button for data.
- The bot can crawl web pages and use this data.
- The Inbox page has two tabs: Virtual Assistant and Live Chat.
- Global Search allows searching records and settings across all pages.
- After most actions, the page displays a notification indicating the status of the action.
"""


bug_report_template = """
Bug name:
Steps:
Actual result:
Expected:
"""

def generate_bug_report(text: str) -> str:
    logger.debug("Creating formatting")
    context_block = project_context if use_project_context else ""
    prompt = f"""
    Convert the user's message into a bug report.

    {context_block}

    Use the following format exactly:
    {bug_report_template}

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


def show_bug_report_template() -> str:
    logger.debug("Show bug report template")
    return bug_report_template


def edit_bug_report_template(text: str) -> str:
    logger.debug("Editing bug report template")
    return "NOT_IMPLEMENTED"


def show_project_overview() -> str:
    logger.debug("Show project overview")
    return project_context


def update_project_overview(text: str) -> str:
    logger.debug("Updating project overview")
    return "NOT_IMPLEMENTED"


def set_use_documentation(flag: bool) -> str:
    logger.debug(f"Use documentation flag: {flag}")
    use_project_context = flag
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
