import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
from openai import OpenAI

# Environment variables
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Initialize Slack & OpenAI
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
slack_client = app.client
openai_client = OpenAI(api_key=OPENAI_API_KEY)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# Dynamically fetch bot ID
BOT_ID = slack_client.auth_test()["user_id"]

# Keywords
GRAMMAR_KEYWORDS = ["fix text", "check grammar", "check", "verify text"]
BUG_KEYWORDS = ["create bug", "create jira defect", "create defect"]
KNOWLEDGE_KEYWORDS = ["what is", "how", "where", "can we", "can I"]

# Load knowledge base facts
with open("knowledge.txt", "r") as f:
    KNOWLEDGE_FACTS = [line.strip() for line in f if line.strip()]

def contains_keyword(text, keywords):
    text_lower = text.lower()
    return any(k in text_lower for k in keywords)

def find_fact(text):
    """Return first fact that appears in the text, or None."""
    text_lower = text.lower()
    for fact in KNOWLEDGE_FACTS:
        # If any keyword from the fact is in the text
        for word in fact.lower().split():
            if word in text_lower:
                return fact
    return None

# Respond to mentions
@app.event("app_mention")
def mention(event, say):
    text = event.get("text", "")
    channel = event.get("channel")
    user = event.get("user")

    if not user:
        return  # ignore bot messages

    # Remove bot mention
    text = text.replace(f"<@{BOT_ID}>", "").strip()

    # Grammar check
    if contains_keyword(text, GRAMMAR_KEYWORDS):
        prompt = f"Check grammar, return fixed text only: {text}"
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that fixes grammar."},
                    {"role": "user", "content": prompt}
                ]
            )
            corrected_text = response.choices[0].message.content.strip()
            say(corrected_text)
        except Exception as e:
            say(f"Failed to check grammar: {e}")
        return

    # Bug creation (stub)
    if contains_keyword(text, BUG_KEYWORDS):
        say("Bug creation command received. Implementation pending.")
        return

    # Knowledge base
    if contains_keyword(text, KNOWLEDGE_KEYWORDS):
        # Combine all facts into a single context string
        context = "\n".join(KNOWLEDGE_FACTS)
        prompt = f"""
    Answer the question ONLY using the facts below. Keep it short. 
    If the question cannot be answered with these facts, reply "IDK answer".

    Facts:
    {context}

    Question:
    {text}
    """
        try:
            response = openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a concise and helpful assistant."},
                    {"role": "user", "content": prompt}
                ]
            )
            answer = response.choices[0].message.content.strip()
            say(answer)
        except Exception as e:
            say(f"Failed to get answer: {e}")
        return

    # Default echo
    say(f"Received: {text}")

# Slack events endpoint
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

# Healthcheck endpoint
@flask_app.route("/", methods=["GET"])
def ping():
    return {"status": "ok"}

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=3000, debug=True)
