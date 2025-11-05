# commands.py
import os
from openai import OpenAI
from src.jira_client import get_open_bugs_from_epic
from src.knowledge import KNOWLEDGE_BASE
from src.logger import logger

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# ----------------------------------
# Helpers
# ----------------------------------

def contains(text: str, keywords: list[str]) -> bool:
    return any(k in text for k in keywords)

# ----------------------------------
# (1) Grammar fixing command
# ----------------------------------

def handle_grammar_request(text: str) -> str:
    logger.debug("Handling 'grammar' command")
    prompt = f"Fix grammar and return corrected text only:\n{text}"

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()

# ----------------------------------
# (2) Knowledge base command
# ----------------------------------

def handle_knowledge_request(text: str) -> str:
    logger.debug("Handling 'knowledge' command")
    # Find a matching fact
    for fact in KNOWLEDGE_BASE:
        if fact.lower() in text.lower():
            prompt = f"Short answer based only on this fact: {fact}"
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0
            )
            return response.choices[0].message.content.strip()

    return "IDK answer"

# ----------------------------------
# (3) Jira: get open bugs
# ----------------------------------

def handle_jira_open_bugs() -> str:
    logger.debug("Handling 'jira' command")
    bugs, error = get_open_bugs_from_epic()

    if error:
        return f"Jira error: {error}"

    if not bugs:
        return "No open bugs found in this epic."

    return "*Open bugs:*\n" + "\n".join(f"- {b}" for b in bugs)
