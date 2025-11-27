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
from src.utils import contains

# Slack app setup
slack_app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)


# Main event handler
@slack_app.event("app_mention")
def handle_mention(event, say):
    text = event.get("text", "").lower()

    if len(text) < 2:
        say("Hmm :)")
        return

    # Show bug report template
    if contains(text, ["show bug report", "bug report template"]):
        say(show_bug_report_template())
        return

    # Generate bug report
    if contains(text, ["generate bug", "bug report", "format bug"]):
        say(generate_bug_report(text))
        return

    # Help
    if contains(text, ["info", "help", "commands"]):
        say(get_help())
        return

    # Edit bug report template
    if contains(text, ["edit bug report", "bug report template"]):
        say(edit_bug_report_template(text))
        return

    # Show project overview
    if contains(text, ["show project", "project details", "project info", "about the project", "about project"]):
        say(show_project_overview())
        return

    # Update project overview
    if contains(text, ["update project", "update docs", "update specs", "update documentation"]):
        say(update_project_overview(text))
        return

    # Use project overview for bug report generation
    if contains(text, ["use docs", "use documentation", "use project documentation", "enable doces"]):
        set_use_documentation(True)
        say("Bot will use project documentation")
        return

    # Use project overview for bug report generation
    if contains(text, ["ignore docs", "ignore documentation", "ignore project documentation", "disable docs"]):
        set_use_documentation(False)
        say("Bot will use project documentation")
        return

    # Default fallback
    logger.error(f'Failed to recognise the command: {text}')
    say("I did not understand that command.")


@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


# Healthcheck endpoint
@flask_app.route("/", methods=["GET"])
def ping():
    return {"status": "ok"}


if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000)
