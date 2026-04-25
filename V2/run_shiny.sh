#!/usr/bin/env bash
# Run the Travel Dashboard Shiny app from any directory.
# Usage: ./run_shiny.sh   OR   bash run_shiny.sh
# First time: cd shiny_app && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT/shiny_app"
echo "Using: $(pwd)"
exec shiny run app.py --reload "$@"
