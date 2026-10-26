"""Probe: does the simulated visitor miss the confirmation number?

Feeds the visitor the SAME booking exchange many times (a fixed opening and a
fixed bot confirmation that clearly includes the number), once per style, and
counts how often its next message claims the number is missing or asks for it.

Calls OpenAI directly (via SimulatedUser's raw HTTP); nothing goes to Raindrop.
Cost: about $0.01 for the default 30 trials per style.

  python -m harness.probe_sim            # 30 trials per style
  python -m harness.probe_sim --n 50

Every reply is saved to runs/<timestamp>-probe/probe.jsonl so the automatic
classification can be checked by eye.
"""

import argparse
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .scenarios import Scenario
from .simulated_user import DONE, STYLES, SimulatedUser

# The personas that showed the problem in earlier runs, plus two that didn't.
PERSONAS = [
    "a busy parent planning a family trip; brief, a little impatient",
    "an experienced backpacker who knows the parks and gets annoyed by vague answers",
    "a retired teacher who writes long, polite messages",
    "a first-time visitor from overseas; formal English, asks clarifying questions",
    "a trail runner who wants quick facts and nothing else",
    "a couple planning an anniversary trip; friendly and chatty",
]
GOAL = ("Book a campsite at Yosemite for the night of 2027-06-08 for 6 people, "
        "reservation under the name Hannah.")
OPENING = ("Hi, I need to book a campsite at Yosemite for June 8, 2027, for six people. "
           "Can you put it under Hannah?")
CONFIRMATION_REPLY = """Your campsite has been successfully booked at Yosemite National Park! Here are the details:

- **Campground:** Upper Pines
- **Site Number:** C15
- **Date:** June 8, 2027
- **Party Size:** 6
- **Amenities:** Flush toilets, drinking water, fire rings, bear lockers
- **Reservation Name:** Hannah
- **Confirmation Number:** NPS-57201

Enjoy your trip! 🌲🏕️"""

# "Claims missing / asks for it again": talks about the confirmation without
# quoting the number back, and either negates or asks.
_MENTIONS = re.compile(r"confirm(ation)?\s*(number|#|code|details)|reference number", re.I)
_MISSING = re.compile(
    r"didn.?t (catch|get|receive|see)|did not (catch|get|receive|see)|haven.?t (got|gotten|received|seen)"
    r"|never (got|received)|not (yet )?received|again|resend|send (me|it)|what (is|was) (the|my)"
    r"|can (you|i) (get|have)|could (you|i) (get|have|provide|share)|please (provide|share|send)",
    re.I)


def classify(reply: str) -> str:
    if "NPS-57201" in reply:
        return "quotes_number"          # it clearly saw the number
    if _MENTIONS.search(reply) and (_MISSING.search(reply) or "?" in reply):
        return "claims_missing"         # the failure we're measuring
    if DONE in reply:
        return "done"
    return "other"


def trial(style: str, i: int) -> dict:
    persona = PERSONAS[i % len(PERSONAS)]
    sim = SimulatedUser(Scenario(scenario_id=f"probe{i:03d}", target_bug=None,
                                 persona=persona, goal=GOAL), style=style)
    sim.transcript.append({"role": "assistant", "content": OPENING})  # visitor's opening
    reply = sim.react(CONFIRMATION_REPLY)
    return {"style": style, "trial": i, "persona": persona, "reply": reply,
            "label": classify(reply), "usage": sim.usage}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30, help="trials per style")
    p.add_argument("--workers", type=int, default=8)
    args = p.parse_args()
    load_dotenv()

    jobs = [(style, i) for style in STYLES for i in range(args.n)]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda job: trial(*job), jobs))

    out_dir = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}-probe"
    out_dir.mkdir(parents=True)
    with open(out_dir / "probe.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    tok_in = sum(r["usage"]["input"] for r in results)
    tok_out = sum(r["usage"]["output"] for r in results)
    print(f"\n{args.n} trials per style. Labels per style:\n")
    for style in STYLES:
        counts = Counter(r["label"] for r in results if r["style"] == style)
        missing = counts.get("claims_missing", 0)
        print(f"  {style:<11} claims_missing={missing:>3} ({missing / args.n:.0%})  "
              + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())
                          if k != "claims_missing"))
    print(f"\nEstimated cost: ${tok_in * 0.15e-6 + tok_out * 0.60e-6:.4f}")
    print(f"All replies: {out_dir}/probe.jsonl  (spot-check the labels!)")


if __name__ == "__main__":
    main()
