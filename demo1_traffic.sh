#!/usr/bin/env bash
# Demo 1 (Nov 19 presentation): the story's traffic, paced, both phases in one run.
#
#   Phase 1 "bug":   glacier_mixup on, app v1   (PHASE_SECONDS, default 90 min)
#   Phase 2 "fixed": all bugs off,     app v2   (same length, starts right away: no gap)
#
# Both phases use --mix demo1 (half Glacier visitors, half ordinary ones), so only the bug flag
# changes at the fix. It runs one batch (harness.run, unchanged) with a new seed, then sleeps for the
# rest of the interval. To look less mechanical, each batch picks a random size (N_MIN..N_MAX,
# default 2-6, average 4) and a random interval (EVERY_MIN..EVERY_MAX seconds, default 4-8 min,
# average 6). A failed batch is logged and the loop goes on.
#
# Times (local and UTC, for the fixed-range bookmark) go to demo1-times.txt.
#
# Run from anywhere, in the background:
#   nohup ~/projects/park_demo/demo1_traffic.sh > ~/projects/park_demo/demo1_traffic.log 2>&1 &
# Watch:   tail -f ~/projects/park_demo/demo1_traffic.log
# Stop:    pkill -f demo1_traffic.sh   (a batch already running finishes on its own)
#
# Settings (env): PHASE_SECONDS=5400 N_MIN=2 N_MAX=6 EVERY_MIN=240 EVERY_MAX=480 SEED=1000
#                 DRY_RUN=0 PYTHON=.venv/bin/python

set -u
cd "$(dirname "$0")"

PHASE_SECONDS=${PHASE_SECONDS:-5400}
N_MIN=${N_MIN:-2}
N_MAX=${N_MAX:-6}
EVERY_MIN=${EVERY_MIN:-240}
EVERY_MAX=${EVERY_MAX:-480}
SEED=${SEED:-1000}
DRY_RUN=${DRY_RUN:-0}
PYTHON=${PYTHON:-.venv/bin/python}
TIMES=demo1-times.txt

extra=()
[ "$DRY_RUN" = "1" ] && extra=(--dry-run)

stamp() {  # "<what>  <local time>  <UTC time in the UI's bookmark format>"
  printf '%-14s %s   UTC %s\n' "$1" "$(date '+%a %Y-%m-%d %H:%M:%S %Z')" "$(date -u '+%Y-%m-%dT%H:%M:%S')" | tee -a "$TIMES"
}

between() {  # a random whole number from $1 to $2, inclusive
  echo $(( $1 + RANDOM % ($2 - $1 + 1) ))
}

trap 'stamp "stopped"; exit 130' INT TERM

run_phase() {  # run_phase <label> <bugs> <app version>
  local label=$1 bugs=$2 version=$3
  local end=$(( $(date +%s) + PHASE_SECONDS ))
  while [ "$(date +%s)" -lt "$end" ]; do
    local started n every
    started=$(date +%s)
    n=$(between "$N_MIN" "$N_MAX")
    every=$(between "$EVERY_MIN" "$EVERY_MAX")
    echo "--- $(date '+%H:%M:%S') phase=$label seed=$SEED n=$n next in ${every}s bugs=${bugs:-none} version=$version"
    if ! "$PYTHON" -m harness.run --n "$n" --mix demo1 --bugs "$bugs" --app-version "$version" \
         --seed "$SEED" --label "demo1-$label-s$SEED" "${extra[@]}"; then
      echo "!!! batch failed (seed $SEED); continuing"
    fi
    SEED=$((SEED + 1))
    local left=$(( every - ($(date +%s) - started) ))
    # Don't sleep past the end of the phase.
    local to_end=$(( end - $(date +%s) ))
    [ "$left" -gt "$to_end" ] && left=$to_end
    [ "$left" -gt 0 ] && sleep "$left"
  done
}

echo "=== $(date) demo1 traffic | phase ${PHASE_SECONDS}s each | batches of $N_MIN-$N_MAX every $EVERY_MIN-${EVERY_MAX}s | dry_run=$DRY_RUN"
stamp "phase1 start"
run_phase bug glacier_mixup v1
stamp "fix (phase2)"
run_phase fixed "" v2
stamp "end"
echo "=== done. Times are in $TIMES"
