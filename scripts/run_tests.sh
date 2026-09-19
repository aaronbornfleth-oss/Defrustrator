#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export MOZAIK_SAMPLE_PDF="$ROOT/samples/Spigener-report-2026-09-15-1000.pdf"
cd "$ROOT/backend"
python3 -m unittest discover -p 'test_*.py' "$@"
