"""Render a run's transcripts.jsonl as human-readable Markdown (transcripts.md).

run.py calls render() at the end of every batch. To (re)render an older run:
  python -m harness.render runs/<timestamp>-<label>
"""

import json
import sys
from pathlib import Path

MAX_TOOL_OUTPUT = 300  # characters; long tool outputs are cut for readability


def _short(obj) -> str:
    text = json.dumps(obj, ensure_ascii=False)
    return text if len(text) <= MAX_TOOL_OUTPUT else text[:MAX_TOOL_OUTPUT] + "…"


def _quote(text: str) -> list[str]:
    """Blockquote a possibly multi-line message so lists inside it stay intact."""
    return ["> " + line if line else ">" for line in text.splitlines()] or [">"]


def _header(r: dict) -> list[str]:
    fired = ", ".join(r["bugs_fired"]) or "none"
    return [
        f"## {r['scenario_id']} · target: {r['target_bug'] or 'clean'} · fired: {fired} "
        f"· {r['outcome']} ({r['turns']} turns)",
        "",
        f"- **Persona:** {r['persona']}",
        f"- **Goal:** {r['goal']}",
        f"- **convo_id:** `{r['convo_id']}` · app_version {r['app_version']}",
        "",
    ]


def _turns(r: dict) -> list[str]:
    lines = []
    if "turn_log" in r:
        for i, t in enumerate(r["turn_log"], 1):
            lines += [f"**Visitor ({i}):** {t['user']}", ""]
            for tool in t["tools"]:
                err = f"  \n  ⚠️ **error:** {tool['error']}" if tool.get("error") else ""
                lines += [f"- 🔧 `{tool['name']}` {_short(tool['input'])}  \n"
                          f"  → {_short(tool['output'])}{err}", ""]
            lines += ["**Bot:**", "", *_quote(t["reply"]), ""]
    else:  # runs made before tool logging: visitor/bot text only
        for m in r.get("transcript", []):
            if m["role"] == "visitor":
                lines += [f"**Visitor:** {m['text']}", ""]
            else:
                lines += ["**Bot:**", "", *_quote(m["text"]), ""]
    return lines


def render(run_dir) -> Path:
    run_dir = Path(run_dir)
    records = [json.loads(line) for line in
               (run_dir / "transcripts.jsonl").read_text().splitlines() if line.strip()]
    records.sort(key=lambda r: r["scenario_id"])  # file order is completion order

    lines = [f"# Transcripts: {run_dir.name}", "",
             f"{len(records)} conversations. Raindrop never sees this file.", ""]
    for r in records:
        lines += _header(r) + _turns(r) + ["---", ""]

    out = run_dir / "transcripts.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python -m harness.render runs/<run-folder>")
    print(f"Wrote {render(sys.argv[1])}")
