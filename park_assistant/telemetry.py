"""Telemetry backends for the Park Trip Assistant.

The chatbot only talks to a small interface, so the backend can be swapped:

    interaction = telemetry.begin(...)   # start of one user turn
    interaction.track_tool(...)          # once per tool call in that turn
    interaction.finish(output=reply)     # end of the turn

Backends:
  * laminar   - one trace per turn, grouped into a session per conversation
  * raindrop  - the original Raindrop SDK (one event per turn)
  * dry run   - nothing is sent anywhere (any backend with dry_run=True)

Why a wrapper:
  * dry-run mode: run everything without sending anything,
  * one place that counts turns (one begin()/finish() pair = one event or trace),
  * keeps the chatbot code readable.
"""

import os
import threading
import time

BACKENDS = ("laminar", "raindrop")


class _NullInteraction:
    id = "dry-run"

    def track_tool(self, **kwargs):
        pass

    def set_properties(self, props):
        pass

    def finish(self, output=None, **extra):
        pass


def make_telemetry(backend: str = "laminar", dry_run: bool = False):
    if backend == "laminar":
        return LaminarTelemetry(dry_run=dry_run)
    if backend == "raindrop":
        return RaindropTelemetry(dry_run=dry_run)
    raise ValueError(f"unknown telemetry backend {backend!r}; choose from {BACKENDS}")


# --------------------------------------------------------------------------- Raindrop

class RaindropTelemetry:
    name = "raindrop"

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


# Backwards-compatible name for older imports.
Telemetry = RaindropTelemetry


# --------------------------------------------------------------------------- Laminar

class _LaminarInteraction:
    """One user turn = one Laminar trace.

    Trace shape:
        park_chat            root span: input = the visitor's message, output = the reply
          openai.chat        LLM spans from auto-instrumentation (full message history)
          <tool name>        TOOL spans: input = arguments, output = result
    The trace's session ID is the conversation ID; its user ID is the visitor ID.
    """

    def __init__(self, span):
        self._span = span
        self.id = str(span.get_span_context().trace_id)
        self.finished = False

    def track_tool(self, *, name, input, output, duration_ms, error=None):
        from lmnr import Laminar
        from opentelemetry.trace import Status, StatusCode

        # The tool already ran; back-date the span so its timing is real.
        end_ns = time.time_ns()
        start_ns = end_ns - int(duration_ms * 1_000_000)
        span = Laminar.start_span(name, input=input, span_type="TOOL", start_time=start_ns)
        span.set_output(output)
        if error is not None:
            span.record_exception(error)
            span.set_status(Status(StatusCode.ERROR, str(error)))
        span.end(end_time=end_ns)

    def set_properties(self, props):
        pass  # properties are set as trace metadata in begin()

    def finish(self, output=None, **extra):
        if self.finished:
            return
        self._span.set_output(output)
        self._span.end()
        self.finished = True

    def abandon(self, reason: str):
        """End a turn that raised before finish(), so its span doesn't stay open."""
        from opentelemetry.trace import Status, StatusCode
        if self.finished:
            return
        self._span.set_status(Status(StatusCode.ERROR, reason))
        self._span.end()
        self.finished = True


class LaminarTelemetry:
    name = "laminar"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.events_sent = 0
        self._lock = threading.Lock()
        self._local = threading.local()  # the open turn in each worker thread
        if not dry_run:
            from lmnr import Instruments, Laminar
            Laminar.initialize(
                project_api_key=os.environ["LMNR_PROJECT_API_KEY"],
                base_url=os.environ.get("LMNR_BASE_URL", "http://localhost"),
                http_port=int(os.environ.get("LMNR_HTTP_PORT", "8000")),
                grpc_port=int(os.environ.get("LMNR_GRPC_PORT", "8001")),
                instruments={Instruments.OPENAI},  # only the app's OpenAI calls
            )

    def begin(self, *, user_id: str, convo_id: str, user_input: str, properties: dict,
              model: str, tools: list):
        with self._lock:
            self.events_sent += 1
        if self.dry_run:
            return _NullInteraction()
        from lmnr import Laminar

        # If this thread's previous turn raised before finish(), close it now.
        # Otherwise every later span in this thread would nest under it.
        prev = getattr(self._local, "interaction", None)
        if prev is not None and not prev.finished:
            prev.abandon("turn raised before finish()")

        span = Laminar.start_active_span(
            "park_chat",
            input=user_input,
            user_id=user_id,
            session_id=convo_id,
            metadata={**{k: str(v) for k, v in properties.items()}, "model": model},
        )
        interaction = _LaminarInteraction(span)
        self._local.interaction = interaction
        return interaction

    def shutdown(self):
        if not self.dry_run:
            from lmnr import Laminar
            Laminar.flush()
            Laminar.shutdown()
