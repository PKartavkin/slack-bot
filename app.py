import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from starlette.concurrency import run_in_threadpool

from src.logger import logger
from src.commands import (
    generate_bug_report,
    get_help,
    update_project_overview,
    set_use_documentation,
    show_project_overview,
    edit_bug_report_template,
    show_bug_report_template,
    set_jira_token,
    set_jira_url,
    set_jira_bug_query,
    show_jira_bug_query,
)
from src.metrics import increment_bot_invocations
from src.utils import contains, strip_command

# Slack app setup
slack_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"],
    # Ensure Slack gets an ACK within 3 seconds even if processing is longer
    process_before_response=True,
)

fastapi_app = FastAPI()
handler = SlackRequestHandler(slack_app)


# Main event handler
@slack_app.event("app_mention")
def handle_mention(event, say, body):
    text = event.get("text", "").lower()
    team_id = body.get("team_id") or event.get("team", {}).get("id")

    MAX_TEXT_LENGTH = 4000
    MIN_PROJECT_OVERVIEW_LENGTH = 50
    MIN_BUG_REPORT_TEMPLATE_LENGTH = 25

    if len(text) < 2:
        say("Hmm :)")
        return

    if len(text) > MAX_TEXT_LENGTH:
        say(
            f"Your message is too long ({len(text)} characters). "
            f"Please shorten it to under {MAX_TEXT_LENGTH} characters."
        )
        return

    # Show bug report template
    if contains(text, ["show bug report", "bug report template"]):
        say(show_bug_report_template(team_id))
        return

    # Generate bug report
    if contains(text, ["generate bug", "bug report", "format bug"]):
        say(generate_bug_report(text, team_id))
        return

    # Help
    if contains(text, ["info", "help", "commands"]):
        say(get_help())
        return

    # Edit bug report template
    edit_bug_report_template_keywords = ["edit bug report", "bug report template"]
    if contains(text, edit_bug_report_template_keywords):
        payload = strip_command(text, edit_bug_report_template_keywords)
        if len(payload) < MIN_BUG_REPORT_TEMPLATE_LENGTH:
            say(
                f"Bug report template is too short. "
                f"Must be at least {MIN_BUG_REPORT_TEMPLATE_LENGTH} characters."
            )
            return
        say(edit_bug_report_template(payload, team_id))
        return

    # Show project overview
    if contains(
        text,
        [
            "show project",
            "project details",
            "project info",
            "about the project",
            "about project",
        ],
    ):
        say(show_project_overview(team_id))
        return

    # Update project overview
    update_project_overview_keywords = [
        "update project",
        "update docs",
        "update specs",
        "update documentation",
    ]
    if contains(text, update_project_overview_keywords):
        payload = strip_command(text, update_project_overview_keywords)
        if len(payload) < MIN_PROJECT_OVERVIEW_LENGTH:
            say(
                f"Project description is too short. "
                f"Must be at least {MIN_PROJECT_OVERVIEW_LENGTH} characters."
            )
            return
        say(update_project_overview(payload, team_id))
        return

    # Use project overview for bug report generation
    if contains(
        text,
        [
            "use docs",
            "use documentation",
            "use project documentation",
            "enable doces",
        ],
    ):
        set_use_documentation(True, team_id)
        say("Bot will use project documentation")
        return

    # Ignore project overview for bug report generation
    if contains(
        text,
        [
            "ignore docs",
            "ignore documentation",
            "ignore project documentation",
            "disable docs",
        ],
    ):
        set_use_documentation(False, team_id)
        say("Bot won't use project documentation")
        return

    # Set Jira Token
    if contains(text, ["set jira token", "update jira token"]):
        say(set_jira_token(text, team_id))
        return

    # Set Jira URL
    if contains(text, ["set jira url", "update jira url"]):
        say(set_jira_url(text, team_id))
        return

    # Set Jira Bug Query
    if contains(text, ["set jira query", "jira bug query", "update jira query"]):
        say(set_jira_bug_query(text, team_id))
        return

    # Show Jira Bug Query
    if contains(text, ["show jira query", "show bug query", "jira query"]):
        say(show_jira_bug_query(team_id))
        return

    # Default fallback
    logger.error(f"Failed to recognise the command: {text}")
    say("I did not understand that command.")


@fastapi_app.post("/slack/events")
async def slack_events(request: Request):
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="No JSON received")

    team_id = data.get("team_id") or (data.get("team") or {}).get("id")
    if team_id:
        # Offload MongoDB write to thread pool so we don't block the event loop.
        await run_in_threadpool(increment_bot_invocations, team_id)

    # Delegate to Slack Bolt FastAPI handler
    response = await handler.handle(request)
    # handler.handle returns a Starlette Response; return as-is
    return response


@fastapi_app.get("/")
async def ping():
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app:fastapi_app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 3000)),
        reload=os.getenv("ENV") != "prod",
    )
