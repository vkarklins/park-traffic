"""Planted-bug switches and the "which bugs fired" recorder.

Every planted bug is:
  1. OFF by default (so the app behaves correctly until we decide otherwise),
  2. switched on by name, e.g. BugConfig(enabled={"large_party"}),
  3. recorded when it actually affects a conversation (BugRecorder.fire),
     which is how the harness builds its answer key.

The hook functions at the bottom are where each bug gets injected. Right now
they are deliberate pass-throughs (no bug behavior yet). We'll fill them in
together, one at a time.

Raindrop never sees anything in this file. The answer key stays local.
"""

import datetime
from dataclasses import dataclass, field

ALL_BUGS = {
    "large_party":  "#1 Booking fails for parties over 6 (over 3 in v2; real limit is 8)",
    "date_shift":   "#2 Booking tool saves Fri/Sat-night dates one day later (trace-only)",
    "forgetting":   "#3 Model only sees the last 2 prior turns of the chat",
    "glacier_mixup": "#4 'Glacier' resolves to Glacier Bay (AK) instead of Glacier (MT)",
    "timeout":      "#5 Park details lookup times out for one park",
}


@dataclass
class BugConfig:
    enabled: set = field(default_factory=set)
    timeout_park: str = "olympic"  # which park bug #5 affects
    app_version: str = "v1"        # bug #1 gets worse in v2 (the "regression")

    def on(self, name: str) -> bool:
        return name in self.enabled


@dataclass
class BugRecorder:
    """Collects the bugs that actually changed behavior during one conversation."""
    fired: set = field(default_factory=set)

    def fire(self, name: str) -> None:
        self.fired.add(name)


# ---------------------------------------------------------------------------
# Bug hooks. Each one currently returns the CORRECT behavior.
# ---------------------------------------------------------------------------

def hook_resolve_park(query: str, correct_key: str | None,
                      bugs: BugConfig, rec: BugRecorder) -> str | None:
    """Bug #4: "Glacier" (Montana) resolves to Glacier Bay (Alaska).

    Only fires when the correct answer is Glacier MT, so a visitor who says
    "Glacier Bay" is unaffected. Silent: the tool succeeds, for the wrong park.
    """
    if bugs.on("glacier_mixup") and correct_key == "glacier":
        rec.fire("glacier_mixup")
        return "glacier bay"
    return correct_key


def hook_park_details(park_key: str, bugs: BugConfig, rec: BugRecorder) -> str | None:
    """Bug #5: the park-details lookup for one park always times out.

    Returns an error message for get_park_details to raise as a ToolError, or
    None to continue. Always fails for that park (not intermittent), so the
    rare cluster is consistent.
    """
    if bugs.on("timeout") and park_key == bugs.timeout_park:
        rec.fire("timeout")
        return "Park details service timed out after 30s."
    return None


# Bug #1's wrong limit per app version; the real one is MAX_PARTY_SIZE (8) in data.py.
# v2 is the regression: the limit drops to 3, so ordinary parties of 4-6 start failing
# across clean, date-shift and forgetting conversations.
BUGGY_PARTY_LIMIT = {"v1": 6, "v2": 3}
WEEKEND_NIGHTS = {4, 5}  # Friday and Saturday nights (date.weekday(): Mon=0 ... Sun=6)
HISTORY_WINDOW = 2       # bug #3: prior turns the model still sees


def hook_booking_party(party_size: int, bugs: BugConfig, rec: BugRecorder) -> str | None:
    """Bug #1: reject parties over the wrong limit (6 in v1, 4 in v2).

    Returns an error message for book_campsite to raise as a ToolError, or None
    to let the booking continue. The real limit (8) is checked before this
    hook, so only parties the real limit allows can be wrongly rejected here.
    """
    limit = BUGGY_PARTY_LIMIT[bugs.app_version]
    if bugs.on("large_party") and party_size > limit:
        rec.fire("large_party")
        return f"Party size {party_size} exceeds the {limit}-person site limit."
    return None


def hook_booking_date(date: str, bugs: BugConfig, rec: BugRecorder) -> str:
    """Bug #2: Friday/Saturday-night bookings are saved one day later. Silent: no error.

    Same in v1 and v2 (the v2 regression is on bug #1). The bot tends to repeat
    the date the visitor asked for, so this usually shows only in the trace:
    tool input date vs. tool output date.
    An unparseable date is returned unchanged and the bug does NOT fire, so
    this bug can never turn into a tool error.
    """
    if not bugs.on("date_shift"):
        return date
    try:
        requested = datetime.date.fromisoformat(date)
    except (TypeError, ValueError):
        return date
    if requested.weekday() not in WEEKEND_NIGHTS:
        return date
    rec.fire("date_shift")
    return (requested + datetime.timedelta(days=1)).isoformat()


def hook_history(history: list, bugs: BugConfig, rec: BugRecorder) -> list:
    """Bug #3: the model only sees the last HISTORY_WINDOW prior turns.

    `history` is a flat list of messages: user, assistant (possibly with
    tool_calls), tool results, assistant reply. We cut only at a user message:
    OpenAI rejects a request where a tool result appears without the assistant
    tool_calls message that requested it.

    Fires whenever something is dropped, which means "truncation happened",
    not "truncation caused a failure". It applies to every conversation that
    runs past HISTORY_WINDOW + 1 turns, not only the forgetting scenario.
    """
    if not bugs.on("forgetting"):
        return history
    user_starts = [i for i, m in enumerate(history) if m["role"] == "user"]
    if len(user_starts) <= HISTORY_WINDOW:
        return history
    rec.fire("forgetting")
    return history[user_starts[-HISTORY_WINDOW]:]
