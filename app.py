import os

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from slack_bolt import App
from slack_bolt.adapter.fastapi import SlackRequestHandler
from starlette.concurrency import run_in_threadpool

from src.logger import logger
from src.config import validate_environment_variables
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
    set_jira_email,
    set_jira_defaults,
    show_jira_defaults,
    clear_jira_default,
    test_jira_connection,
    get_jira_bugs,
    get_settings,
    get_channel_welcome_shown,
    set_channel_welcome_shown,
    set_channel_project,
    list_projects,
    show_channel_status,
)
from src.metrics import increment_bot_invocations
from src.utils import contains, strip_command, strip_leading_mention

# Validate environment variables at startup
validate_environment_variables()

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
    raw_text = event.get("text", "") or ""
    # Strip leading '<@BOTID>' mention so length checks and commands work on real text.
    clean_text = strip_leading_mention(raw_text)
    text = clean_text.lower()
    team_id = body.get("team_id") or event.get("team", {}).get("id")
    channel_id = event.get("channel")
    
    MIN_TEXT_LENGTH = 3
    MAX_TEXT_LENGTH = 1000
    MIN_PROJECT_OVERVIEW_LENGTH = 50
    MIN_BUG_REPORT_TEMPLATE_LENGTH = 25

    # Per-channel welcome message on first mention in that channel
    if team_id and channel_id:
        welcome_shown = get_channel_welcome_shown(team_id, channel_id)
        if not welcome_shown:
            say(
                "👋 Hi! I'm your QA helper bot. I can:\n"
                "- Format your messages into structured bug reports\n"
                "- Store project documentation and use it when generating bugs\n"
                "- Help you manage Jira-related settings\n\n"
                "Type *help* or *info* in a mention to see available commands."
            )
            set_channel_welcome_shown(team_id, channel_id, True)
            return

    if len(clean_text) < MIN_TEXT_LENGTH:
        say("Hmm :)")
        return

    if len(clean_text) > MAX_TEXT_LENGTH:
        say(
            f"Your message is too long ({len(clean_text)} characters). "
            f"Please shorten it to under {MAX_TEXT_LENGTH} characters."
        )
        return


    # Project configuration selection / discovery
    if contains(text, ["list projects"]):
        say(list_projects(team_id))
        return

    if contains(text, ["use project"]):
        if not channel_id:
            say("I couldn't detect the channel for this request.")
            return
        say(set_channel_project(clean_text, team_id, channel_id))
        return

    # Show channel status
    if contains(text, ["status"]):
        say(show_channel_status(team_id, channel_id))
        return

    # Show bug report template
    if contains(text, ["show bug template"]):
        say(show_bug_report_template(team_id, channel_id=channel_id))
        return

    # Generate bug report
    if contains(text, ["create bug report"]):
        # Pass channel_id so project-specific configuration is used if set.
        say(generate_bug_report(clean_text, team_id, channel_id=channel_id))
        return

    # Help
    if contains(text, ["help"]):
        say(get_help())
        return

    # Edit bug report template
    if contains(text, ["edit bug template"]):
        payload = strip_command(clean_text, "edit bug template")
        if len(payload) < MIN_BUG_REPORT_TEMPLATE_LENGTH:
            say(
                f"Bug report template is too short. "
                f"Must be at least {MIN_BUG_REPORT_TEMPLATE_LENGTH} characters."
            )
            return
        say(edit_bug_report_template(clean_text, team_id, channel_id=channel_id))
        return

    # Show project overview
    if contains(text, ["show project"]):
        say(show_project_overview(team_id, channel_id=channel_id))
        return

    # Update project overview
    if contains(text, ["update docs"]):
        payload = strip_command(clean_text, "update docs")
        if len(payload) < MIN_PROJECT_OVERVIEW_LENGTH:
            say(
                f"Project description is too short. "
                f"Must be at least {MIN_PROJECT_OVERVIEW_LENGTH} characters."
            )
            return
        say(update_project_overview(clean_text, team_id, channel_id=channel_id))
        return

    # Use project overview for bug report generation
    if contains(text, ["enable docs"]):
        set_use_documentation(True, team_id, channel_id=channel_id)
        say("Bot will use project documentation")
        return

    # Ignore project overview for bug report generation
    if contains(text, ["disable docs"]):
        set_use_documentation(False, team_id, channel_id=channel_id)
        say("Bot won't use project documentation")
        return

    # Set Jira Token
    if contains(text, ["set jira token"]):
        say(set_jira_token(clean_text, team_id, channel_id=channel_id))
        return

    # Set Jira URL
    if contains(text, ["set jira url"]):
        say(set_jira_url(clean_text, team_id, channel_id=channel_id))
        return

    # Set Jira Bug Query
    if contains(text, ["set jira query"]):
        say(set_jira_bug_query(clean_text, team_id, channel_id=channel_id))
        return

    # Show Jira Bug Query
    if contains(text, ["show jira query"]):
        say(show_jira_bug_query(team_id, channel_id=channel_id))
        return

    # Set Jira Email
    if contains(text, ["set jira email"]):
        say(set_jira_email(clean_text, team_id, channel_id=channel_id))
        return

    # Set Jira Defaults
    if contains(text, ["set jira defaults"]):
        say(set_jira_defaults(clean_text, team_id, channel_id=channel_id))
        return

    # Show Jira Defaults
    if contains(text, ["show jira defaults"]):
        say(show_jira_defaults(team_id, channel_id=channel_id))
        return

    # Clear Jira Default
    if contains(text, ["clear jira default"]):
        say(clear_jira_default(clean_text, team_id, channel_id=channel_id))
        return

    # Test Jira Connection
    if contains(text, ["test jira"]):
        say(test_jira_connection(team_id, channel_id=channel_id))
        return

    # Get Jira Bugs
    if contains(text, ["get bugs"]):
        say(get_jira_bugs(team_id, channel_id=channel_id))
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
