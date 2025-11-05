# app.py
import os
from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from src.commands import (
    handle_grammar_request,
    handle_knowledge_request,
    handle_jira_open_bugs,
    contains,
)

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

    # (1) Grammar check commands
    if contains(text, ["fix text", "check grammar", "verify text", "grammar"]):
        response = handle_grammar_request(text)
        say(response)
        return

    # (2) Knowledge base Q&A
    if contains(text, ["what is", "how", "where", "can we", "can i"]):
        kb_response = handle_knowledge_request(text)
        say(kb_response)
        return

    # (3) Jira: Get open bugs in epic
    if contains(text, ["get open bugs", "list open bugs", "show open bugs"]):
        response = handle_jira_open_bugs()
        say(response)
        return

    # Default fallback
    say("I did not understand that command.")

# Slack events endpoint
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

# Healthcheck endpoint
@flask_app.route("/", methods=["GET"])
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000)
