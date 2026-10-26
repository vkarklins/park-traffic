# Park Trip Assistant + traffic harness (Raindrop failure-clustering demo)

A small chatbot with planted bugs, plus a harness that runs simulated visitors
against it so Raindrop has realistic, varied conversations to cluster.

## Layout

```
park_assistant/        the app under test (what Raindrop sees)
  data.py              stub parks, trails, sold-out dates (the "truth")
  tools.py             5 tools the model can call
  chatbot.py           one conversation; each turn = one Raindrop event
  telemetry.py         Raindrop wrapper: dry-run mode + event counter
  bugs.py              planted-bug switches + hook points (all OFF / pass-through)
harness/               the fake users around the app (Raindrop never sees this)
  scenarios.py         personas, goals, target bug per scenario, traffic mixes
  simulated_user.py    LLM that role-plays a visitor (raw HTTP, so not traced)
  run.py               runs a batch, enforces the event cap, writes the answer key
  render.py            turns transcripts.jsonl into readable transcripts.md
runs/                  output of each batch (answer key, transcripts, summary)
```

## How one conversation works

1. `run.py` takes a scenario from the deck (persona + goal + target bug).
2. `SimulatedUser` writes an opening message in character.
3. `ParkAssistant.respond()` opens a Raindrop interaction (`begin`), lets the
   model call tools (each logged with `track_tool`), then `finish`es it.
   **One `respond()` call = one Raindrop event.**
4. The simulated user reacts. Repeat until it writes `[DONE]` or `[GIVE_UP]`.
   After 6 turns, its next message is sent as the last one. Every final
   message is sent to the bot (markers stripped), so Raindrop sees every
   ending, happy or frustrated. Worst case: 7 events per conversation.
5. `BugRecorder` notes which planted bugs actually fired. That plus the
   target bug goes to `answer_key.jsonl`, which stays local.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in both keys; RAINDROP_PROJECT_ID keeps this data separate
```

## Running

```bash
# 1. Dry run: calls OpenAI, sends NOTHING to Raindrop (~$0.01)
python -m harness.run --n 3 --dry-run --label dry

# 2. Smoke test: clean traffic, real events (~40 events)
python -m harness.run --n 10 --mix clean --label smoke --max-events 60

# 3. Baseline batch (after bugs are designed)
python -m harness.run --n 130 --mix baseline --bugs all --label baseline --max-events 700

# 4. "v2 deploy" batch (Tuesday)
python -m harness.run --n 90 --mix baseline --bugs all --app-version v2 --label v2 --seed 1 --max-events 400
```

Flags: `--workers` (parallel conversations, default 4), `--seed` (deck randomness),
`--bugs large_party,date_shift` (enable specific bugs).

## Event budget

`--max-events` is a hard cap. Before starting a conversation, the runner
reserves its worst case (7 events) and gives back what it didn't use, so
parallel workers can't overshoot. Each run prints events sent, token usage,
and estimated OpenAI cost in `summary.json`.

## Reading transcripts

Every run writes `transcripts.md` next to `transcripts.jsonl`: one section per
conversation with the scenario, target bug, bugs that fired, outcome, and each
turn's tool calls (inputs, outputs, errors). Open it in VS Code's Markdown
preview. To re-render an older run: `python -m harness.render runs/<run-folder>`.
