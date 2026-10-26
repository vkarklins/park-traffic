"""The Park Trip Assistant: the "app under test".

One ParkAssistant instance = one conversation. Each call to respond() is one
user turn, and is wrapped in a Raindrop interaction (begin -> finish), which
Raindrop records as one event. Inside a turn the model may call tools several
times; each tool call is logged explicitly with interaction.track_tool(), so
its input, output and errors show up in the trace no matter what
auto-instrumentation captures.

This file knows nothing about simulated users or the answer key.
"""

import json
import time

from . import bugs as b
from .tools import TOOL_FUNCTIONS, TOOL_SCHEMAS, ToolContext, ToolError

MODEL = "gpt-4o-mini"
MAX_LLM_CALLS_PER_TURN = 5

SYSTEM_PROMPT = """You are the Park Trip Assistant for US national parks.
You can look up parks by state, describe parks, report trail status, check
campsite availability, and book one-night standard campsites.
Always use the tools for facts; never invent trail status or availability.
Before booking, confirm park, date (YYYY-MM-DD), party size, and the name for
the reservation. When confirming a booking, state the details exactly as the
booking tool returned them. Keep replies short and friendly. The current year
is 2027."""


class ParkAssistant:
    def __init__(self, *, client, telemetry, bugs: b.BugConfig, rec: b.BugRecorder,
                 user_id: str, convo_id: str, app_version: str = "v1"):
        self.client = client
        self.telemetry = telemetry
        self.bugs = bugs
        self.rec = rec
        self.user_id = user_id
        self.convo_id = convo_id
        self.app_version = app_version
        # Prior turns as the model saw them: user messages, assistant tool calls,
        # tool results, and final replies. Keeping the tool messages is what lets
        # the model remember it already booked something.
        self.history: list[dict] = []
        # Local record of every turn, tool calls included, for our transcripts.
        # (Raindrop gets the same tool info through track_tool spans.)
        self.turns: list[dict] = []
        self.usage = {"input": 0, "output": 0}
        # One tool context for the whole conversation (holds the booking counter).
        self.ctx = ToolContext(bugs=bugs, rec=rec)

    def respond(self, user_msg: str) -> str:
        interaction = self.telemetry.begin(
            user_id=self.user_id, convo_id=self.convo_id, user_input=user_msg,
            properties={"app_version": self.app_version},
            model=MODEL, tools=TOOL_SCHEMAS,
        )
        ctx = self.ctx
        turn_tools: list[dict] = []

        visible_history = b.hook_history(self.history, self.bugs, self.rec)
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    *visible_history,
                    {"role": "user", "content": user_msg}]
        turn_start = len(messages) - 1  # this turn's messages begin at its user message

        reply = ""
        for _ in range(MAX_LLM_CALLS_PER_TURN):
            resp = self.client.chat.completions.create(
                model=MODEL, messages=messages, tools=TOOL_SCHEMAS, temperature=0.3)
            self.usage["input"] += resp.usage.prompt_tokens
            self.usage["output"] += resp.usage.completion_tokens
            msg = resp.choices[0].message

            if not msg.tool_calls:
                reply = msg.content or ""
                break

            messages.append({
                "role": "assistant", "content": msg.content,
                "tool_calls": [{"id": tc.id, "type": "function",
                                "function": {"name": tc.function.name,
                                             "arguments": tc.function.arguments}}
                               for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                result = self._run_tool(tc.function.name, tc.function.arguments, ctx,
                                        interaction, turn_tools)
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result)})
        else:
            reply = "Sorry, I'm having trouble with that right now. Could you try again?"

        interaction.finish(output=reply)
        self.turns.append({"user": user_msg, "tools": turn_tools, "reply": reply})
        messages.append({"role": "assistant", "content": reply})
        # Save this whole turn (from its user message on) to the full history.
        # self.history is never truncated; hook_history only limits what the
        # model sees on the next turn.
        self.history += messages[turn_start:]
        return reply

    def _run_tool(self, name, raw_args, ctx, interaction, turn_tools) -> dict:
        start = time.perf_counter()
        error = None
        try:
            args = json.loads(raw_args or "{}")
        except json.JSONDecodeError:
            args = {"_raw": raw_args}
        try:
            fn = TOOL_FUNCTIONS[name]
            output = fn(args, ctx)
        except ToolError as e:
            error = e
            output = {"error": str(e)}
        except Exception as e:  # bad args from the model, etc.
            error = e
            output = {"error": f"{type(e).__name__}: {e}"}
        duration_ms = (time.perf_counter() - start) * 1000

        span = {"name": name, "input": args, "output": output, "duration_ms": duration_ms}
        if error is not None:
            span["error"] = error
        interaction.track_tool(**span)
        turn_tools.append({**span, "error": str(error) if error is not None else None})
        return output
