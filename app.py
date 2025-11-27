import os
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from src.logger import logger

from src.commands import (
    generate_bug_report,
    get_help, update_project_overview, set_use_documentation, show_project_overview, edit_bug_report_template,
    show_bug_report_template,
)
from src.metrics import increment_bot_invocations
from src.utils import contains, strip_command

# Slack app setup
slack_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)

# Main event handler
@slack_app.event("app_mention")
def handle_mention(event, say, body):
    text = event.get("text", "").lower()
    team_id = body.get("team_id") or event.get("team", {}).get("id")

    MIN_PROJECT_OVERVIEW_LENGTH = 50
    MIN_BUG_REPORT_TEMPLATE_LENGTH = 25

    if len(text) < 2:
        say("Hmm :)")
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
            say(f"Bug report template is too short. Must be at least {MIN_BUG_REPORT_TEMPLATE_LENGTH} characters.")
            return
        say(edit_bug_report_template(payload, team_id))
        return

    # Show project overview
    if contains(text, ["show project", "project details", "project info", "about the project", "about project"]):
        say(show_project_overview(team_id))
        return

    # Update project overview
    update_project_overview_keywords = ["update project", "update docs", "update specs", "update documentation"]
    if contains(text, update_project_overview_keywords):
        payload = strip_command(text, update_project_overview_keywords)
        if len(payload) < MIN_PROJECT_OVERVIEW_LENGTH:
            say(f"Project description is too short. Must be at least {MIN_PROJECT_OVERVIEW_LENGTH} characters.")
            return
        say(update_project_overview(payload, team_id))
        return

    # Use project overview for bug report generation
    if contains(text, ["use docs", "use documentation", "use project documentation", "enable doces"]):
        set_use_documentation(True, team_id)
        say("Bot will use project documentation")
        return

    # Ignore project overview for bug report generation
    if contains(text, ["ignore docs", "ignore documentation", "ignore project documentation", "disable docs"]):
        set_use_documentation(False, team_id)
        say("Bot won't use project documentation")
        return

    # Default fallback
    logger.error(f'Failed to recognise the command: {text}')
    say("I did not understand that command.")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.json
    if not data:
        return "No JSON received", 400

    team_id = data.get("team_id") or data.get("team", {}).get("id")
    if team_id:
        increment_bot_invocations(team_id)

    return handler.handle(request)


# Healthcheck endpoint
@flask_app.route("/", methods=["GET"])
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000)
