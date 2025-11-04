import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# Respond to mentions
@app.event("app_mention")
def mention(event, say):
    say(f"Received: {event['text']}")

# Route for Slack events
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

# Healthcheck
@flask_app.route("/", methods=["GET"])
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000, debug=True)
