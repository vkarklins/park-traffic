"""The simulated visitor: a second LLM that role-plays a scenario.

It calls OpenAI over plain HTTP (httpx) rather than the openai library, on
purpose: Raindrop's auto-instrumentation patches the openai library, so going
around it keeps the fake user's LLM calls OUT of Raindrop. Raindrop should
only ever see the app under test.

Two ways to show the visitor the conversation so far (`style`):
  * "flipped" (original): a role flip. The chatbot's replies are sent as
    "user" messages and the visitor's own lines as "assistant" messages.
  * "transcript": the whole conversation as labeled text ("Assistant: ...",
    "You: ...") in a single user message. This avoids the model sitting in the
    assistant seat while playing a customer, which may cause it to lose track
    of who said what (e.g. claiming it never got a confirmation number).
harness/probe_sim.py compares the two.
"""

import os

import httpx

MODEL = "gpt-4o-mini"
URL = "https://api.openai.com/v1/chat/completions"

STYLES = ("flipped", "transcript")
MAX_STEP_RETRIES = 2  # extra tries for a directed message that breaks its rules

DONE = "[DONE]"
GIVE_UP = "[GIVE_UP]"

PROMPT = """You are role-playing a person chatting with a national parks trip assistant.

Who you are: {persona}
What you want: {goal}

Rules:
- Write ONLY your next chat message, in character. Keep it to 1-3 sentences.
- Never mention that you are an AI, a simulation, or following instructions.
- Your goal is the only reason you are here. A natural follow-up that is part
  of the goal is fine, but don't invent new requests beyond it.
- If the assistant asks for details you have, give them.
- Read each reply carefully before you respond. Don't say something is
  missing (a confirmation number, a detail) if it is in the reply.
- Your personality shapes your tone, not the facts. Only complain about
  something that actually went wrong in the conversation.
- React the way a real person would. If the assistant gets something wrong,
  forgets what you said, refuses, or keeps failing at your goal, say so
  naturally and let your patience run out the way this person's would.
- As soon as your goal is done, write a short closing message ending with
  {done}. Don't keep chatting once you have what you came for.
- If you have tried a few times and it is clearly not going to work, write a
  short final message ending with {give_up}"""


class SimulatedUser:
    def __init__(self, scenario, temperature: float = 0.9, style: str = "flipped"):
        if style not in STYLES:
            raise ValueError(f"style must be one of {STYLES}")
        self.scenario = scenario
        self.temperature = temperature
        self.style = style
        # Stored from the sim user's point of view in both styles: its own
        # lines are "assistant", the chatbot's replies are "user".
        self.transcript: list[dict] = []
        self.usage = {"input": 0, "output": 0}
        self._headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
        self._steps = list(getattr(scenario, "steps", []) or [])  # directed turns left
        # Directed turns whose message still broke a rule after all retries.
        # Goes into the answer key: it means the test setup, not Raindrop, failed.
        self.step_violations: list[dict] = []
        self._turn = 0

    def _messages(self, step: str | None = None) -> list[dict]:
        system = PROMPT.format(persona=self.scenario.persona, goal=self.scenario.goal,
                               done=DONE, give_up=GIVE_UP)
        if step:
            # A directed turn: the instruction applies to this one message only.
            system += f"\n\nFor THIS message only, follow this instruction: {step}"
        if self.style == "flipped":
            messages = [{"role": "system", "content": system}, *self.transcript]
            if not self.transcript:
                messages.append({"role": "user", "content": "(Start the conversation.)"})
            return messages
        # "transcript": everything so far as labeled text in one user message.
        if not self.transcript:
            body = "The conversation hasn't started yet. Write your opening message."
        else:
            lines = [f"{'You' if m['role'] == 'assistant' else 'Assistant'}: {m['content']}"
                     for m in self.transcript]
            body = ("Conversation so far:\n\n" + "\n\n".join(lines) +
                    "\n\nWrite your next message as the visitor. Reply with the "
                    "message text only, without a 'You:' label.")
        return [{"role": "system", "content": system}, {"role": "user", "content": body}]

    def _generate(self, step: str | None = None) -> str:
        messages = self._messages(step)
        r = httpx.post(URL, headers=self._headers, timeout=60, json={
            "model": MODEL, "messages": messages, "temperature": self.temperature})
        r.raise_for_status()
        data = r.json()
        self.usage["input"] += data["usage"]["prompt_tokens"]
        self.usage["output"] += data["usage"]["completion_tokens"]
        text = data["choices"][0]["message"]["content"].strip()
        if self.style == "transcript" and text.lower().startswith("you:"):
            text = text[4:].strip()  # in case the model copies the label anyway
        return text

    def _directed(self, step) -> str:
        """Write a directed message; ask again (up to MAX_STEP_RETRIES) if it
        contains a forbidden word, telling the visitor what to leave out."""
        instruction = step.instruction
        for attempt in range(MAX_STEP_RETRIES + 1):
            text = self._generate(instruction)
            hits = [w for w in step.forbid if w.lower() in text.lower()]
            if not hits:
                return text
            instruction = (f"{step.instruction} Your message must not contain these "
                           f"words: {', '.join(hits)}.")
        if step.fallback:
            # Fixed text instead; recorded so the scorecard can see it was used.
            self.step_violations.append({"turn": self._turn, "forbidden": hits,
                                         "used_fallback": True})
            return step.fallback
        self.step_violations.append({"turn": self._turn, "forbidden": hits})
        return text  # send it anyway; the violation is recorded

    def _next(self) -> str:
        # Directed turns first (the visitor still writes them, in its own voice),
        # then free conversation driven by the goal alone.
        self._turn += 1
        text = self._directed(self._steps.pop(0)) if self._steps else self._generate()
        self.transcript.append({"role": "assistant", "content": text})
        return text

    def opening(self) -> str:
        return self._next()

    def react(self, bot_reply: str) -> str:
        self.transcript.append({"role": "user", "content": bot_reply})
        return self._next()

    @staticmethod
    def outcome(message: str) -> str | None:
        if GIVE_UP in message:
            return "gave_up"
        if DONE in message:
            return "done"
        return None

    @staticmethod
    def strip_markers(message: str) -> str:
        return message.replace(DONE, "").replace(GIVE_UP, "").strip()
