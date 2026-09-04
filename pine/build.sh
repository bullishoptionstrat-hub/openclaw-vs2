#!/usr/bin/env bash
# Assemble the two TradingView scripts from the shared parts so the detection
# logic and confluence engine cannot drift between the indicator and strategy.
set -euo pipefail
cd "$(dirname "$0")"

IND="openclaw-ict-confluence-indicator.pine"
STR="openclaw-ict-confluence-strategy.pine"

cat parts/00-header-indicator.pine parts/10-engine.pine parts/20-visuals.pine parts/30-alerts-indicator.pine > "$IND"
cat parts/00-header-strategy.pine  parts/10-engine.pine parts/20-visuals.pine parts/30-execution-strategy.pine > "$STR"

# Guard: the shared block must be byte-identical in both generated scripts.
extract() { awk '/SHARED CONFLUENCE ENGINE — BEGIN/,/SHARED VISUAL LAYER/' "$1"; }
if ! diff <(extract "$IND") <(extract "$STR") > /dev/null; then
  echo "ERROR: shared engine drifted between builds" >&2
  exit 1
fi
echo "built: $IND ($(wc -l < "$IND") lines), $STR ($(wc -l < "$STR") lines) — shared engine identical"
