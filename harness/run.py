"""Run a batch of simulated conversations against the Park Trip Assistant.

Examples (from the park_demo folder):
  python -m harness.run --n 3 --dry-run                     # nothing sent to Raindrop
  python -m harness.run --n 10 --mix clean --label smoke     # real smoke test
  python -m harness.run --n 130 --mix baseline --bugs all --label baseline --max-events 700

Outputs go to runs/<timestamp>-<label>/:
  answer_key.jsonl   one line per conversation: target bug, bugs that fired, outcome
  transcripts.jsonl  full conversations incl. tool calls, for our own inspection
  transcripts.md     the same conversations, human-readable (see harness/render.py)
  summary.json       counts, events sent, token usage, estimated cost
"""

import argparse
import json
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from park_assistant.bugs import ALL_BUGS, BugConfig, BugRecorder
from park_assistant.chatbot import ParkAssistant
from park_assistant.telemetry import Telemetry

from .render import render
from .scenarios import MIX_BASELINE, MIX_CLEAN, MIX_FORGETTING, build_deck
from .simulated_user import STYLES, SimulatedUser

PRICE_IN, PRICE_OUT = 0.15 / 1e6, 0.60 / 1e6  # gpt-4o-mini, USD per token
MIXES = {"baseline": MIX_BASELINE, "clean": MIX_CLEAN, "forgetting": MIX_FORGETTING}


class EventBudget:
    """Reserve a conversation's worst-case events up front so threads can't overshoot."""

    def __init__(self, cap: int | None):
        self.cap = cap
        self.reserved = 0
        self._lock = threading.Lock()

    def reserve(self, n: int) -> bool:
        with self._lock:
            if self.cap is not None and self.reserved + n > self.cap:
                return False
            self.reserved += n
            return True

    def release(self, n: int) -> None:
        with self._lock:
            self.reserved -= n


def run_conversation(scenario, *, client, telemetry, bug_config, app_version, budget,
                     sim_style="flipped"):
    # max_turns ordinary turns, plus one final message if the visitor is still
    # going at the limit (so Raindrop sees every ending).
    worst_case = scenario.max_turns + 1
    if not budget.reserve(worst_case):
        return None  # skipped: would exceed the event cap

    rec = BugRecorder()
    bot = ParkAssistant(client=client, telemetry=telemetry, bugs=bug_config, rec=rec,
                        user_id=f"visitor-{scenario.scenario_id}",
                        convo_id=f"convo-{uuid.uuid4()}", app_version=app_version)
    user = SimulatedUser(scenario, style=sim_style)

    user_msg = user.opening()
    outcome, turns = "turn_limit", 0
    while True:
        ended = SimulatedUser.outcome(user_msg)  # "done", "gave_up", or None
        # Every visitor message is sent, including the last one (happy or angry),
        # so Raindrop sees how every conversation ended.
        reply = bot.respond(SimulatedUser.strip_markers(user_msg))
        turns += 1
        if ended:
            outcome = ended
            break
        if turns > scenario.max_turns:
            break  # that was the visitor's final message after hitting the limit
        user_msg = user.react(reply)

    budget.release(worst_case - turns)
    return {
        "convo_id": bot.convo_id, "user_id": bot.user_id,
        "scenario_id": scenario.scenario_id, "target_bug": scenario.target_bug,
        "bugs_fired": sorted(rec.fired), "outcome": outcome, "turns": turns,
        "step_violations": user.step_violations,
        "app_version": app_version, "persona": scenario.persona, "goal": scenario.goal,
        "usage_bot": bot.usage, "usage_user": user.usage,
        "turn_log": bot.turns,  # [{user, tools: [{name, input, output, error, ...}], reply}]
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=3, help="number of conversations")
    p.add_argument("--mix", choices=MIXES, default="clean")
    p.add_argument("--bugs", default="", help="comma list of bug names, or 'all'")
    p.add_argument("--app-version", default="v1")
    p.add_argument("--label", default="run")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-events", type=int, default=None, help="hard cap on Raindrop events")
    p.add_argument("--dry-run", action="store_true", help="don't send anything to Raindrop")
    p.add_argument("--sim-style", choices=STYLES, default="flipped",
                   help="how the simulated visitor sees the conversation (see probe_sim.py)")
    args = p.parse_args()

    load_dotenv()
    enabled = set(ALL_BUGS) if args.bugs == "all" else {b for b in args.bugs.split(",") if b}
    unknown = enabled - set(ALL_BUGS)
    if unknown:
        p.error(f"unknown bugs: {unknown}. Known: {list(ALL_BUGS)}")

    out_dir = Path("runs") / f"{datetime.now():%Y%m%d-%H%M%S}-{args.label}"
    out_dir.mkdir(parents=True)
    deck = build_deck(args.n, MIXES[args.mix], seed=args.seed)
    telemetry = Telemetry(dry_run=args.dry_run)
    client = OpenAI()
    bug_config = BugConfig(enabled=enabled, app_version=args.app_version)
    budget = EventBudget(args.max_events)

    print(f"Running {len(deck)} conversations | mix={args.mix} | bugs={sorted(enabled) or 'none'} "
          f"| version={args.app_version} | {'DRY RUN' if args.dry_run else 'SENDING TO RAINDROP'}")
    t0 = time.time()
    results, skipped = [], 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_conversation, s, client=client, telemetry=telemetry,
                               bug_config=bug_config, app_version=args.app_version,
                               budget=budget, sim_style=args.sim_style) for s in deck]
        for f in as_completed(futures):
            try:
                r = f.result()
            except Exception as e:  # one broken conversation shouldn't kill the batch
                print(f"  ! conversation failed: {type(e).__name__}: {e}")
                continue
            if r is None:
                skipped += 1
                continue
            results.append(r)
            print(f"  [{len(results):>3}] {r['scenario_id']} target={r['target_bug']} "
                  f"fired={r['bugs_fired']} {r['outcome']} ({r['turns']} turns) "
                  f"| events so far: {telemetry.events_sent}")

    telemetry.shutdown()

    tok_in = sum(r["usage_bot"]["input"] + r["usage_user"]["input"] for r in results)
    tok_out = sum(r["usage_bot"]["output"] + r["usage_user"]["output"] for r in results)
    summary = {
        "label": args.label, "mix": args.mix, "bugs_enabled": sorted(enabled),
        "app_version": args.app_version, "dry_run": args.dry_run, "sim_style": args.sim_style,
        "conversations": len(results), "skipped_for_event_cap": skipped,
        "events_sent": 0 if args.dry_run else telemetry.events_sent,
        "outcomes": dict(Counter(r["outcome"] for r in results)),
        "target_bugs": dict(Counter(str(r["target_bug"]) for r in results)),
        "bugs_fired": dict(Counter(b for r in results for b in r["bugs_fired"])),
        "convos_with_step_violations": sum(1 for r in results if r["step_violations"]),
        "tokens": {"input": tok_in, "output": tok_out},
        "est_openai_cost_usd": round(tok_in * PRICE_IN + tok_out * PRICE_OUT, 4),
        "seconds": round(time.time() - t0, 1),
    }
    with open(out_dir / "answer_key.jsonl", "w") as f:
        for r in results:
            key = {k: r[k] for k in ("convo_id", "user_id", "scenario_id", "target_bug",
                                     "bugs_fired", "outcome", "turns", "step_violations",
                                     "app_version")}
            f.write(json.dumps(key) + "\n")
    with open(out_dir / "transcripts.jsonl", "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    render(out_dir)

    print("\n" + json.dumps(summary, indent=2))
    print(f"\nSaved to {out_dir}/")


if __name__ == "__main__":
    main()
