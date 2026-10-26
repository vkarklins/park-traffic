"""Thin wrapper around the Raindrop SDK.

Why a wrapper:
  * dry-run mode: run everything without sending a single event to Raindrop,
  * one place that counts events (one begin()/finish() pair = one event),
  * keeps the chatbot code readable.
"""

import os
import threading


class _NullInteraction:
    id = "dry-run"

    def track_tool(self, **kwargs):
        pass

    def set_properties(self, props):
        pass

    def finish(self, output=None, **extra):
        pass


class Telemetry:
    def __init__(self, dry_run: bool = False, project_id: str | None = None):
        self.dry_run = dry_run
        # Raindrop project slug; unset means the default "Production" project.
        project_id = project_id or os.environ.get("RAINDROP_PROJECT_ID") or None
        self.events_sent = 0
        self._lock = threading.Lock()
        self._rd = None
        if not dry_run:
            import raindrop.analytics as raindrop
            key = os.environ["RAINDROP_WRITE_KEY"]
            kwargs = {"tracing_enabled": True}  # auto-instrument OpenAI -> LLM spans
            if project_id:
                kwargs["project_id"] = project_id
            raindrop.init(key, **kwargs)
            self._rd = raindrop

    def begin(self, *, user_id: str, convo_id: str, user_input: str, properties: dict,
              model: str, tools: list):
        with self._lock:
            self.events_sent += 1
        if self.dry_run:
            return _NullInteraction()
        return self._rd.begin(user_id=user_id, event="park_chat", input=user_input,
                              convo_id=convo_id, properties=properties,
                              model=model, tools=tools)

    def shutdown(self):
        if self._rd:
            self._rd.flush()
            self._rd.shutdown()
