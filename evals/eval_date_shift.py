"""Eval: does the park assistant report the booking date the tool actually returned?

Dataset: date-shift booking turns labeled in Laminar. Each datapoint's data is
the openai.chat span's input: the message history ending with the
book_campsite result.

Run from park_demo:  python -m evals.eval_date_shift
"""
import datetime
import json

from dotenv import load_dotenv
from lmnr import LaminarDataset, evaluate
from openai import OpenAI

from park_assistant.chatbot import MODEL, SYSTEM_PROMPT
from park_assistant.tools import TOOL_SCHEMAS

load_dotenv()

DATASET = "test"  # the dataset's name in Laminar
# Run 1: leave empty. Run 2: try the fix.
# EXTRA_RULE = ""
EXTRA_RULE = ("If any booking detail the tool returned differs from what the "
              "user asked for, point out the difference.")

client = OpenAI()


def get_messages(data) -> list[dict]:
    """Pull the message list out of a datapoint. Fails loudly on an unknown shape."""
    if isinstance(data, list):
        return data
    for key in ("messages", "input"):
        if isinstance(data, dict) and key in data:
            return data[key]
    raise ValueError(f"Unexpected datapoint shape: {type(data).__name__}, "
                     f"keys={list(data) if isinstance(data, dict) else None}")


def booked_date(messages: list[dict]) -> str:
    """The date book_campsite actually returned (the last booking result)."""
    for m in reversed(messages):
        if m.get("role") != "tool":
            continue
        content = m["content"]
        result = json.loads(content) if isinstance(content, str) else content
        if isinstance(result, dict) and "confirmation" in result and "date" in result:
            return result["date"]
    raise ValueError("No book_campsite result found in this datapoint's messages")


def executor(data) -> dict:
    messages = get_messages(data)
    prompt = SYSTEM_PROMPT + ("\n" + EXTRA_RULE if EXTRA_RULE else "")
    # Swap in the current system prompt; keep the rest of the history as recorded.
    replayed = [{"role": "system", "content": prompt}] + [
        m for m in messages if m.get("role") != "system"]
    resp = client.chat.completions.create(
        model=MODEL, messages=replayed, tools=TOOL_SCHEMAS, temperature=0.3)
    return {"reply": resp.choices[0].message.content or "",
            "tool_date": booked_date(messages)}


def reports_tool_date(output: dict, target) -> int:
    """1 if the reply mentions the tool's date as 2027-07-17 or 'July 17'."""
    d = datetime.date.fromisoformat(output["tool_date"])
    reply = output["reply"]
    return int(d.isoformat() in reply or f"{d:%B} {d.day}" in reply)


evaluate(
    data=LaminarDataset(DATASET),
    executor=executor,
    evaluators={"reports_tool_date": reports_tool_date},
    group_name="date_shift_confirmation",
)
