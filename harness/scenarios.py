"""The scenario deck: who the fake visitors are and what they want.

A scenario = persona (how they talk) + goal (what they want) + a target bug
(which planted failure the scenario is designed to walk into, or None).

The target bug is only an intention. Whether the bug really fired is
recorded separately by BugRecorder during the conversation, and the answer
key stores both.
"""

import random
from dataclasses import dataclass, field

PERSONAS = [
    "a busy parent planning a family trip; brief, a little impatient",
    "a retired teacher who writes long, polite messages",
    "a college student on a budget; casual, uses lowercase and slang",
    "an experienced backpacker who knows the parks and gets annoyed by vague answers",
    "a first-time visitor from overseas; formal English, asks clarifying questions",
    "a scout troop leader organizing a group outing; detail-oriented",
    "a photographer chasing sunrise shots; enthusiastic, a bit scattered",
    "a nurse with limited vacation days; direct and practical",
    "a couple planning an anniversary trip; friendly and chatty",
    "a trail runner who wants quick facts and nothing else",
]

FIRST_NAMES = ["Maria", "James", "Priya", "Tom", "Aiko", "Luis", "Grace", "Dev", "Hannah", "Omar"]

BOOKABLE_PARKS = ["Yosemite", "Zion", "Grand Canyon", "Yellowstone", "Rocky Mountain",
                  "Acadia", "Olympic", "Joshua Tree"]
# Sunday-Thursday nights only: bug #2 (date_shift) leaves these alone in v1.
CLEAN_DATES = ["2027-06-08", "2027-06-15", "2027-07-14", "2027-08-02", "2027-09-09", "2027-09-21"]
# Friday/Saturday nights (none sold out): bug #2 shifts these even in v1.
WEEKEND_DATES = ["2027-06-11", "2027-06-12", "2027-07-16", "2027-07-17", "2027-08-13", "2027-09-17"]
SOLD_OUT_PICKS = [("Yosemite", "2027-07-04"), ("Zion", "2027-05-29"),
                  ("Grand Canyon", "2027-06-19"), ("Yellowstone", "2027-08-14"),
                  ("Acadia", "2027-08-07")]


@dataclass
class Step:
    """One directed turn: an instruction for the visitor's next message, plus words
    the message must not contain (checked case-insensitively; the visitor is asked
    again if one appears). If every try still breaks the rule, `fallback` (when
    set) is sent word for word instead."""
    instruction: str
    forbid: tuple[str, ...] = ()
    fallback: str | None = None


@dataclass
class Scenario:
    scenario_id: str
    target_bug: str | None  # None = clean; "decoy" = frustrated but nothing broken
    persona: str
    goal: str
    max_turns: int = 6
    # Directed turns: one instruction per opening message. The visitor still
    # writes each message in its own voice, but message k must follow steps[k].
    # Used when a scenario needs a turn structure the LLM won't follow from the
    # goal alone (it tends to bundle all its questions into one message).
    # Empty for almost every scenario.
    steps: list[Step] = field(default_factory=list)


def _booking_goal(rng, park, date, party, name, extra=""):
    return (f"Book a campsite at {park} for the night of {date} for {party} people, "
            f"reservation under the name {name}. {extra}").strip()


def make_scenario(i: int, target: str | None, rng: random.Random) -> Scenario:
    persona = rng.choice(PERSONAS)
    name = rng.choice(FIRST_NAMES)
    park = rng.choice(BOOKABLE_PARKS)
    date = rng.choice(CLEAN_DATES)
    steps = []

    if target == "large_party":
        goal = _booking_goal(rng, park, date, rng.choice([7, 8]), name)
    elif target == "date_shift":
        date = rng.choice(WEEKEND_DATES)  # v1 only shifts Friday/Saturday nights
        goal = _booking_goal(rng, park, date, rng.randint(1, 6), name,
                             "Read the confirmation carefully and make sure every detail is right.")
    elif target == "forgetting":
        party = rng.randint(2, 4)  # in v2, parties of 4 also hit bug #1's lowered limit (3)
        # Four directed turns. By turn 4 the buggy history window (2 prior turns)
        # has dropped turn 1, the only place the party size and name appear.
        # Steps 2-4 forbid the name, so at turn 4 the bot must ask for it if it
        # forgot. Steps 2-3 also forbid "book" so the visitor can't jump ahead.
        # Step 3 is a question the bot can't answer early (it sometimes checks
        # campgrounds on its own in turn 1, since it already has the date).
        not_yet = ("If the assistant asked you something, answer it briefly, but don't book "
                   "yet, don't repeat your trip details, and don't end the conversation.")
        steps = [
            Step(f"Give ALL of these details: {park}, the night of {date}, {party} people, "
                 f"reservation name {name}. Say you'll want to book a campsite once you know "
                 f"a bit more. Then ask ONLY what the park is like. Don't ask about trails or "
                 f"campgrounds yet."),
            Step(f"Ask ONLY which trails are open there. {not_yet}", forbid=(name, "book")),
            # "Easiest", not "best for our group": asking about the group invited
            # the visitor to restate the party size here.
            Step(f"Ask ONLY which of those trails is the easiest. {not_yet}",
                 forbid=(name, "book")),
            Step("Tell the assistant to go ahead and book it. Do NOT repeat any of the "
                 "details (park, date, party size, name): you already gave them.",
                 forbid=(name,), fallback="Sounds good, go ahead and book it."),
        ]
        goal = (f"Get a campsite at {park} booked for {date} for {party} people under the name "
                f"{name}, after learning a bit about the park first. You gave all the booking "
                f"details at the start and expect the assistant to remember them. If it asks for "
                f"details you already gave, point out that you told it at the start (you may "
                f"repeat them if it keeps asking).")
    elif target == "glacier_mixup":
        goal = rng.choice([
            "Ask what Glacier National Park in Montana is like and which trails are open. "
            "Call it just 'Glacier'.",
            f"Book a campsite at Glacier (the Montana one) for {date} for "
            f"{rng.randint(2, 5)} people under {name}. Call it just 'Glacier'.",
        ])
    elif target == "timeout":
        goal = "Ask for a description of Olympic National Park and what makes it special."
    elif target == "decoy":
        sp_park, sp_date = rng.choice(SOLD_OUT_PICKS)
        goal = _booking_goal(rng, sp_park, sp_date, rng.randint(2, 6), name,
                             "This date really matters to you; you can't change it.")
    else:  # clean traffic: a mix of ordinary requests
        goal = rng.choice([
            _booking_goal(rng, park, date, rng.randint(1, 6), name),
            f"Ask which national parks are in {rng.choice(['CA', 'UT', 'CO', 'WA'])} and "
            f"get a short description of one of them.",
            f"Ask which trails are open at {park} right now.",
            f"Check whether campsites are available at {park} on {date}.",
        ])

    return Scenario(scenario_id=f"s{i:04d}", target_bug=target, persona=persona, goal=goal,
                    steps=steps)


def build_deck(n: int, mix: dict[str | None, float], seed: int = 0) -> list[Scenario]:
    """Build n scenarios whose target bugs follow the `mix` proportions."""
    rng = random.Random(seed)
    targets = []
    for target, share in mix.items():
        targets += [target] * round(n * share)
    while len(targets) < n:
        targets.append(None)
    targets = targets[:n]
    rng.shuffle(targets)
    return [make_scenario(i, t, rng) for i, t in enumerate(targets)]


# Traffic mixes from the plan. Keys are target bugs (None = clean).
MIX_BASELINE = {"large_party": 0.25, "date_shift": 0.15, "forgetting": 0.15,
                "glacier_mixup": 0.08, "timeout": 0.03, "decoy": 0.10, None: 0.24}
MIX_CLEAN = {None: 1.0}
MIX_FORGETTING = {"forgetting": 1.0}  # for checking the forgetting scenario on its own
